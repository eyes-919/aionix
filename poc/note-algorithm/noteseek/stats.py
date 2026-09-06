"""統計ユーティリティ (依存ライブラリなし).

POC の判定に必要な最小限だけを実装する。
- 相関 (Pearson / Spearman)
- Ridge 回帰 (正規方程式 + ガウス消去)
- ホールドアウト評価 (Spearman / AUC / NDCG@k)

「学習データ上の当てはまり」ではなく「ホールドアウトでの順位相関」を
判定基準にする。過学習した係数を根拠に施策を打たないため。
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

Vector = Sequence[float]
Matrix = Sequence[Sequence[float]]


# -- 記述統計 -----------------------------------------------------------


def mean(values: Vector) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: Vector) -> float:
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    return math.sqrt(sum((v - mu) ** 2 for v in values) / (len(values) - 1))


def pearson(x: Vector, y: Vector) -> float:
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    mx, my = mean(x), mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    if dx == 0.0 or dy == 0.0:
        return 0.0
    return num / (dx * dy)


def rankdata(values: Vector) -> List[float]:
    """同順位は平均順位を与える."""
    indexed = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(indexed):
        end = position
        while (
            end + 1 < len(indexed)
            and values[indexed[end + 1]] == values[indexed[position]]
        ):
            end += 1
        average = (position + end) / 2.0 + 1.0
        for i in range(position, end + 1):
            ranks[indexed[i]] = average
        position = end + 1
    return ranks


def spearman(x: Vector, y: Vector) -> float:
    if len(x) != len(y) or len(x) < 3:
        return 0.0
    return pearson(rankdata(x), rankdata(y))


def spearman_pvalue_approx(rho: float, n: int) -> float:
    """t 近似による両側 p 値。n が小さいときは目安としてのみ使う."""
    if n < 4 or abs(rho) >= 1.0:
        return 0.0 if abs(rho) >= 1.0 else 1.0
    t = rho * math.sqrt((n - 2) / (1 - rho * rho))
    # 正規近似 (自由度が十分あるときの実用的な近似)
    z = abs(t)
    return 2.0 * (1.0 - _normal_cdf(z))


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def auc(labels: Sequence[int], scores: Vector) -> float:
    """ROC AUC (Mann-Whitney U による厳密計算)."""
    positives = [s for s, y in zip(scores, labels) if y == 1]
    negatives = [s for s, y in zip(scores, labels) if y == 0]
    if not positives or not negatives:
        return 0.5
    ranks = rankdata(list(scores))
    positive_rank_sum = sum(r for r, y in zip(ranks, labels) if y == 1)
    n_pos, n_neg = len(positives), len(negatives)
    u = positive_rank_sum - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def ndcg_at_k(relevance_sorted_by_score: Sequence[float], k: int = 10) -> float:
    """スコア降順に並べた真の関連度から NDCG@k を計算する."""
    gains = list(relevance_sorted_by_score)[:k]
    if not gains:
        return 0.0

    def dcg(values: Sequence[float]) -> float:
        return sum(v / math.log2(i + 2) for i, v in enumerate(values))

    ideal = sorted(relevance_sorted_by_score, reverse=True)[:k]
    denominator = dcg(ideal)
    return dcg(gains) / denominator if denominator else 0.0


# -- 標準化 -------------------------------------------------------------


class Standardizer:
    def __init__(self) -> None:
        self.means: List[float] = []
        self.stds: List[float] = []

    def fit(self, matrix: Matrix) -> "Standardizer":
        if not matrix:
            return self
        n_features = len(matrix[0])
        columns = [[row[j] for row in matrix] for j in range(n_features)]
        self.means = [mean(col) for col in columns]
        self.stds = [stdev(col) or 1.0 for col in columns]
        return self

    def transform(self, matrix: Matrix) -> List[List[float]]:
        return [
            [
                (value - self.means[j]) / self.stds[j]
                for j, value in enumerate(row)
            ]
            for row in matrix
        ]

    def transform_row(self, row: Sequence[float]) -> List[float]:
        return [
            (value - self.means[j]) / self.stds[j] for j, value in enumerate(row)
        ]


# -- 線形代数 -----------------------------------------------------------


def solve(matrix: List[List[float]], rhs: List[float]) -> Optional[List[float]]:
    """部分ピボット選択つきガウス消去。特異なら None."""
    n = len(matrix)
    augmented = [list(matrix[i]) + [rhs[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(augmented[r][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            return None
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        for row in range(col + 1, n):
            factor = augmented[row][col] / pivot_value
            if factor == 0.0:
                continue
            for k in range(col, n + 1):
                augmented[row][k] -= factor * augmented[col][k]
    result = [0.0] * n
    for row in range(n - 1, -1, -1):
        total = augmented[row][n] - sum(
            augmented[row][k] * result[k] for k in range(row + 1, n)
        )
        result[row] = total / augmented[row][row]
    return result


class RidgeRegression:
    """L2 正則化つき線形回帰.

    切片を罰則から外すため、説明変数・目的変数とも中心化してから解く。
    中心化を呼び出し側の責務にすると、標準化を通さない入力で
    係数が静かに歪むため、ここで必ず行う。
    """

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self.coefficients: List[float] = []
        self.intercept: float = 0.0
        self.feature_means: List[float] = []

    def fit(self, features: Matrix, target: Vector) -> "RidgeRegression":
        n_samples = len(features)
        if n_samples == 0:
            return self
        n_features = len(features[0])
        y_mean = mean(target)
        centered_y = [value - y_mean for value in target]
        self.feature_means = [
            mean([row[j] for row in features]) for j in range(n_features)
        ]
        centered_x = [
            [row[j] - self.feature_means[j] for j in range(n_features)]
            for row in features
        ]

        gram = [[0.0] * n_features for _ in range(n_features)]
        moment = [0.0] * n_features
        for row, y_value in zip(centered_x, centered_y):
            for i in range(n_features):
                moment[i] += row[i] * y_value
                for j in range(i, n_features):
                    gram[i][j] += row[i] * row[j]
        for i in range(n_features):
            for j in range(i):
                gram[i][j] = gram[j][i]
            gram[i][i] += self.alpha

        solution = solve(gram, moment)
        self.coefficients = solution if solution else [0.0] * n_features
        self.intercept = y_mean
        return self

    def predict_row(self, row: Sequence[float]) -> float:
        return self.intercept + sum(
            c * (v - m)
            for c, v, m in zip(self.coefficients, row, self.feature_means)
        )

    def predict(self, features: Matrix) -> List[float]:
        return [self.predict_row(row) for row in features]


# -- 分割 ---------------------------------------------------------------


def train_test_split(
    n: int, test_ratio: float = 0.3, seed: int = 42
) -> Tuple[List[int], List[int]]:
    indices = list(range(n))
    random.Random(seed).shuffle(indices)
    cut = int(n * (1.0 - test_ratio))
    return indices[:cut], indices[cut:]


def kfold_indices(n: int, folds: int = 5, seed: int = 42) -> List[Tuple[List[int], List[int]]]:
    indices = list(range(n))
    random.Random(seed).shuffle(indices)
    fold_size = max(1, n // folds)
    splits: List[Tuple[List[int], List[int]]] = []
    for f in range(folds):
        start = f * fold_size
        end = n if f == folds - 1 else (f + 1) * fold_size
        test = indices[start:end]
        train = indices[:start] + indices[end:]
        if test and train:
            splits.append((train, test))
    return splits


def describe(values: Vector) -> Dict[str, float]:
    if not values:
        return {"n": 0, "mean": 0.0, "median": 0.0, "p90": 0.0, "max": 0.0}
    ordered = sorted(values)
    def percentile(p: float) -> float:
        idx = min(len(ordered) - 1, int(p * (len(ordered) - 1)))
        return float(ordered[idx])
    return {
        "n": float(len(values)),
        "mean": mean(values),
        "median": percentile(0.5),
        "p90": percentile(0.9),
        "max": float(ordered[-1]),
    }


# 偏相関では統制変数の効果を可能な限り完全に取り除きたいので、
# 正則化は数値安定化のためだけの極小値にする。
RESIDUALIZE_ALPHA = 1e-6

# 残差の標準偏差が元の何倍を下回れば「情報が残っていない」と見なすか
RESIDUAL_VARIANCE_FLOOR = 1e-5


def residualize(
    target: Vector, controls: Matrix, alpha: float = RESIDUALIZE_ALPHA
) -> List[float]:
    """統制変数で説明できる分を取り除いた残差を返す.

    フォロワー数のような支配的な交絡が入っていると、単純な相関では
    「書き手が動かせる要素」の効果が全部そこに吸われる。
    残差に対して相関を取ることで偏相関に相当する量が得られる。
    """
    if not controls or not controls[0]:
        return list(target)
    scaler = Standardizer().fit(controls)
    scaled = scaler.transform(controls)
    model = RidgeRegression(alpha=alpha).fit(scaled, target)
    predictions = model.predict(scaled)
    return [t - p for t, p in zip(target, predictions)]


def partial_spearman(
    x: Vector, y: Vector, controls: Matrix, alpha: float = RESIDUALIZE_ALPHA
) -> float:
    """統制変数の影響を除いた x と y の順位相関."""
    if not controls or not controls[0]:
        return spearman(x, y)
    x_residual = residualize(list(x), controls, alpha)
    y_residual = residualize(list(y), controls, alpha)

    # 統制変数だけで説明し切れてしまった変数は、残差が数値誤差しか持たない。
    # そのまま順位相関を取ると誤差の単調性を拾って +1.0 を返してしまうため、
    # 「情報が残っていない」= 0.0 として扱う。
    for original, residual in ((x, x_residual), (y, y_residual)):
        scale = stdev(list(original))
        if scale > 0.0 and stdev(residual) / scale < RESIDUAL_VARIANCE_FLOOR:
            return 0.0

    return spearman(x_residual, y_residual)
