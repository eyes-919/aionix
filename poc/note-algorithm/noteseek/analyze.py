"""仮説検証と POC 判定.

出力するのは「係数の大きさ」ではなく「ホールドアウトで予測できたか」。
予測できないなら、その特徴量に基づく施策は打つ価値がない、と結論する。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .features import (
    ACTIONABLE_FEATURES,
    CONTROL_FEATURES,
    FEATURE_NAMES,
    FeatureBuilder,
    engagement_target,
    exposure_labels,
)
from .schema import Article
from .stats import (
    RidgeRegression,
    Standardizer,
    auc,
    describe,
    kfold_indices,
    partial_spearman,
    spearman,
    spearman_pvalue_approx,
)

# 判定しきい値。ここを下回るなら「この特徴量セットでは足りない」と読む。
ENGAGEMENT_SPEARMAN_MIN = 0.25
EXPOSURE_AUC_MIN = 0.65
MIN_SAMPLES = 60


@dataclass
class FeatureFinding:
    name: str
    spearman: float
    p_value: float
    coefficient: float
    partial_spearman: float = 0.0
    partial_p_value: float = 1.0
    actionable: bool = True

    @property
    def effect(self) -> float:
        """判断に使う相関。書き手が動かせる変数は交絡を除いた偏相関で見る."""
        return self.partial_spearman if self.actionable else self.spearman

    @property
    def effect_p(self) -> float:
        return self.partial_p_value if self.actionable else self.p_value

    @property
    def significant(self) -> bool:
        return self.effect_p < 0.05 and abs(self.effect) >= 0.1


@dataclass
class ModelReport:
    task: str
    metric_name: str
    holdout_metric: float
    baseline_metric: float
    n_samples: int
    folds: int
    passes: bool
    findings: List[FeatureFinding] = field(default_factory=list)
    note: str = ""


@dataclass
class AnalysisReport:
    n_articles: int
    n_tags: int
    exposure_rate: float
    like_stats: Dict[str, float]
    engagement: Optional[ModelReport]
    exposure: Optional[ModelReport]
    warnings: List[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.n_articles < MIN_SAMPLES:
            return "INSUFFICIENT_DATA"
        passed = [
            report.passes
            for report in (self.engagement, self.exposure)
            if report is not None
        ]
        if not passed:
            return "INSUFFICIENT_DATA"
        if all(passed):
            return "USABLE"
        if any(passed):
            return "PARTIALLY_USABLE"
        return "NOT_USABLE"


def _cv_predict(
    matrix: Sequence[Sequence[float]],
    target: Sequence[float],
    folds: int = 5,
    alpha: float = 1.0,
    seed: int = 42,
) -> List[Optional[float]]:
    """交差検証の out-of-fold 予測を返す. 学習に使っていない点だけを評価する."""
    predictions: List[Optional[float]] = [None] * len(matrix)
    for train_idx, test_idx in kfold_indices(len(matrix), folds=folds, seed=seed):
        train_x = [matrix[i] for i in train_idx]
        train_y = [target[i] for i in train_idx]
        scaler = Standardizer().fit(train_x)
        model = RidgeRegression(alpha=alpha).fit(scaler.transform(train_x), train_y)
        for i in test_idx:
            predictions[i] = model.predict_row(scaler.transform_row(matrix[i]))
    return predictions


def _fit_full(
    matrix: Sequence[Sequence[float]], target: Sequence[float], alpha: float = 1.0
) -> List[float]:
    scaler = Standardizer().fit(matrix)
    model = RidgeRegression(alpha=alpha).fit(scaler.transform(matrix), target)
    return model.coefficients


def _findings(
    matrix: Sequence[Sequence[float]],
    target: Sequence[float],
    coefficients: Sequence[float],
) -> List[FeatureFinding]:
    n = len(matrix)
    control_idx = [FEATURE_NAMES.index(name) for name in CONTROL_FEATURES]
    controls = [[row[j] for j in control_idx] for row in matrix]

    findings: List[FeatureFinding] = []
    for j, name in enumerate(FEATURE_NAMES):
        column = [row[j] for row in matrix]
        rho = spearman(column, list(target))
        actionable = name in ACTIONABLE_FEATURES
        if actionable:
            partial = partial_spearman(column, list(target), controls)
        else:
            partial = rho
        findings.append(
            FeatureFinding(
                name=name,
                spearman=rho,
                p_value=spearman_pvalue_approx(rho, n),
                coefficient=coefficients[j] if j < len(coefficients) else 0.0,
                partial_spearman=partial,
                partial_p_value=spearman_pvalue_approx(partial, n),
                actionable=actionable,
            )
        )
    findings.sort(key=lambda f: abs(f.effect), reverse=True)
    return findings


def analyze(
    articles: Sequence[Article],
    now: Optional[dt.datetime] = None,
    folds: int = 5,
    alpha: float = 1.0,
) -> AnalysisReport:
    warnings: List[str] = []
    n = len(articles)
    if n == 0:
        return AnalysisReport(0, 0, 0.0, describe([]), None, None, ["記事が 0 件"])

    likes = [float(a.like_count) for a in articles]
    labels = exposure_labels(articles)
    exposure_rate = sum(labels) / n

    builder = FeatureBuilder().fit(articles, performance=likes, now=now)
    matrix = builder.matrix(articles)

    if n < MIN_SAMPLES:
        warnings.append(
            f"サンプル数 {n} 件は判定に不足 (推奨 {MIN_SAMPLES} 件以上)"
        )

    engagement_report: Optional[ModelReport] = None
    if n >= 20:
        target = engagement_target(articles)
        predictions = _cv_predict(matrix, target, folds=folds, alpha=alpha)
        paired = [
            (p, t) for p, t in zip(predictions, target) if p is not None
        ]
        holdout = spearman([p for p, _ in paired], [t for _, t in paired])
        # ベースライン: フォロワー数だけで順位づけした場合
        followers = [row[0] for row in matrix]
        baseline = spearman(followers, target)
        coefficients = _fit_full(matrix, target, alpha=alpha)
        engagement_report = ModelReport(
            task="engagement",
            metric_name="holdout_spearman",
            holdout_metric=holdout,
            baseline_metric=baseline,
            n_samples=len(paired),
            folds=folds,
            passes=holdout >= ENGAGEMENT_SPEARMAN_MIN and holdout > baseline,
            findings=_findings(matrix, target, coefficients),
            note="目的変数: log1p(スキ数)。ビュー数は外部から取得できないための代理指標。",
        )
    else:
        warnings.append("反応モデルの学習に必要な件数 (20) に届かない")

    exposure_report: Optional[ModelReport] = None
    positives = sum(labels)
    if n >= 20 and 0 < positives < n:
        float_labels = [float(v) for v in labels]
        predictions = _cv_predict(matrix, float_labels, folds=folds, alpha=alpha)
        paired_idx = [i for i, p in enumerate(predictions) if p is not None]
        scores = [predictions[i] for i in paired_idx]
        truth = [labels[i] for i in paired_idx]
        holdout_auc = auc(truth, scores)
        followers = [matrix[i][0] for i in paired_idx]
        baseline_auc = auc(truth, followers)
        coefficients = _fit_full(matrix, float_labels, alpha=alpha)
        exposure_report = ModelReport(
            task="exposure",
            metric_name="holdout_auc",
            holdout_metric=holdout_auc,
            baseline_metric=baseline_auc,
            n_samples=len(paired_idx),
            folds=folds,
            passes=holdout_auc >= EXPOSURE_AUC_MIN and holdout_auc > baseline_auc,
            findings=_findings(matrix, float_labels, coefficients),
            note="目的変数: 新着プールのうち人気/急上昇タブに現れたか。露出の代理指標。",
        )
    else:
        if positives == 0:
            warnings.append("人気/急上昇に昇格した記事が 0 件。露出モデルを学習できない")
        elif positives == n:
            warnings.append("全記事が露出済み。母集団の取り方を見直す必要がある")
        else:
            warnings.append("露出モデルの学習に必要な件数に届かない")

    tags = {a.source_tag for a in articles if a.source_tag}
    return AnalysisReport(
        n_articles=n,
        n_tags=len(tags),
        exposure_rate=exposure_rate,
        like_stats=describe(likes),
        engagement=engagement_report,
        exposure=exposure_report,
        warnings=warnings,
    )


# -- レポート整形 -------------------------------------------------------


def _format_model(report: ModelReport, top_k: int = 8) -> List[str]:
    lines = [
        f"## {report.task}",
        "",
        report.note,
        "",
        f"- サンプル数: {report.n_samples}",
        f"- 交差検証: {report.folds} fold (out-of-fold 評価)",
        f"- {report.metric_name}: {report.holdout_metric:.3f}",
        f"- ベースライン (フォロワー数のみ): {report.baseline_metric:.3f}",
        f"- 判定: {'PASS' if report.passes else 'FAIL'}",
        "",
        "| 特徴量 | 単純Spearman | 偏Spearman | p値 | Ridge係数 | 種別 | 有意 |",
        "|---|---|---|---|---|---|---|",
    ]
    for finding in report.findings[:top_k]:
        kind = "施策可" if finding.actionable else "統制"
        lines.append(
            f"| {finding.name} | {finding.spearman:+.3f} "
            f"| {finding.partial_spearman:+.3f} | {finding.effect_p:.4f} "
            f"| {finding.coefficient:+.3f} | {kind} "
            f"| {'YES' if finding.significant else 'no'} |"
        )
    lines.append("")
    lines.append(
        "偏Spearman は フォロワー数・投稿数・経過日数 を統制した後の相関。"
        "施策の期待値はこちらで読む。"
    )
    lines.append("")
    return lines


def format_report(report: AnalysisReport) -> str:
    lines = [
        "# note 配信アルゴリズム POC 分析レポート",
        "",
        f"- 判定: {report.verdict}",
        f"- 記事数: {report.n_articles}",
        f"- 対象タグ数: {report.n_tags}",
        f"- 露出率 (新着プール中 人気/急上昇に昇格): {report.exposure_rate:.1%}",
        f"- スキ数 中央値: {report.like_stats['median']:.0f} / "
        f"p90: {report.like_stats['p90']:.0f} / 最大: {report.like_stats['max']:.0f}",
        "",
    ]
    if report.warnings:
        lines.append("## 警告")
        lines.append("")
        for warning in report.warnings:
            lines.append(f"- WARNING: {warning}")
        lines.append("")
    for model in (report.engagement, report.exposure):
        if model is not None:
            lines.extend(_format_model(model))
    lines.extend(
        [
            "## 判定の読み方",
            "",
            f"- USABLE: 反応・露出とも保持ベースライン超え。施策の根拠に使える",
            f"- PARTIALLY_USABLE: 片方のみ。使える側の指標に絞って運用する",
            f"- NOT_USABLE: この特徴量セットでは説明できない。特徴量かデータ設計を変える",
            f"- INSUFFICIENT_DATA: 件数不足。収集を増やす",
            "",
        ]
    )
    return "\n".join(lines)
