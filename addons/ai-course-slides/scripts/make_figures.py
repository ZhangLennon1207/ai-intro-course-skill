# -*- coding: utf-8 -*-
"""生成课件配图（真图，非灰框占位）。

用法：
    python make_figures.py -o out/figs           # 生成全套
    python make_figures.py -o out/figs --only xor,backprop

约定：
- 配色跟课件主题一致（主色 #1F4E79），不另起一套视觉语言。
- 中文用微软雅黑，matplotlib 缺字形会静默变方框，所以出图后有一张 contact 供人看。
- 每张图只讲一件事；标题写在图上，不依赖页面标题，撕下来单看也成立。
"""
import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Circle
import numpy as np

C_MAIN = "#1F4E79"
C_ACC = "#C0504D"
C_ALT = "#4F81BD"
C_GREY = "#8C8C8C"
C_LIGHT = "#EAF0F8"
C_ORANGE = "#E8A33D"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 200
plt.rcParams["savefig.dpi"] = 200


def _clean(ax):
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)


def _box(ax, x, y, w, h, text, fc=C_LIGHT, ec=C_MAIN, fs=13, tc=C_MAIN, bold=True):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=fc, ec=ec, lw=1.6))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, color=tc,
            fontweight="bold" if bold else "normal", linespacing=1.4)


def _arrow(ax, p1, p2, color=C_MAIN, style="-|>", lw=1.6, rad=0.0):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, color=color, lw=lw,
                                 mutation_scale=16,
                                 connectionstyle=f"arc3,rad={rad}"))


# ---------- 1 训练闭环 ----------

def fig_ml_loop(path):
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.set_xlim(0, 10); ax.set_ylim(0, 4.6); _clean(ax)
    _box(ax, 1.5, 3.4, 2.2, 1.0, "训练数据\n(x, y)")
    _box(ax, 5.0, 3.4, 2.2, 1.0, "模型 f(x; θ)")
    _box(ax, 8.4, 3.4, 2.2, 1.0, "预测 ŷ")
    _box(ax, 8.4, 1.2, 2.2, 1.0, "损失 L(ŷ, y)", fc="#FBEEEA", ec=C_ACC, tc=C_ACC)
    _box(ax, 5.0, 1.2, 2.2, 1.0, "梯度 ∂L/∂θ", fc="#FBEEEA", ec=C_ACC, tc=C_ACC)
    _box(ax, 1.5, 1.2, 2.2, 1.0, "更新 θ ← θ − η∂L/∂θ", fc="#FDf3E3", ec=C_ORANGE, tc="#B87322")
    _arrow(ax, (2.6, 3.4), (3.9, 3.4))
    _arrow(ax, (6.1, 3.4), (7.3, 3.4))
    _arrow(ax, (8.4, 2.9), (8.4, 1.7))
    _arrow(ax, (7.3, 1.2), (6.1, 1.2))
    _arrow(ax, (3.9, 1.2), (2.6, 1.2))
    _arrow(ax, (1.5, 1.7), (1.5, 2.9), color=C_ORANGE)
    ax.text(5.0, 4.35, "前向：算预测与损失", ha="center", fontsize=12, color=C_MAIN)
    ax.text(5.0, 0.55, "反向：把损失摊回每个参数", ha="center", fontsize=12, color=C_ACC)
    ax.annotate("", xy=(1.5, 2.75), xytext=(1.5, 1.65),
                arrowprops=dict(arrowstyle="-|>", color=C_ORANGE, lw=2.0,
                                connectionstyle="arc3,rad=0"))
    ax.text(0.55, 2.2, "循环\n收敛", fontsize=11, color=C_ORANGE, va="center", ha="right")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


# ---------- 2 偏差-方差 ----------

def fig_bias_variance(path):
    fig, ax = plt.subplots(figsize=(10, 4.8))
    x = np.linspace(1, 10, 200)
    train = 0.15 + 2.4 * np.exp(-0.55 * x)
    test = 2.0 + 0.06 * (x - 3.2) ** 2 - 1.25 * np.exp(-0.9 * (x - 3.2) ** 2) + 0.9 * np.exp(-1.2 * x)
    test = np.maximum(test, 0.4)
    ax.plot(x, train, color=C_MAIN, lw=2.4, label="训练误差")
    ax.plot(x, test, color=C_ACC, lw=2.4, label="测试误差")
    ax.axvspan(1, 3.0, color="#F2F2F2", zorder=0)
    ax.axvspan(3.0, 5.2, color=C_LIGHT, zorder=0)
    ax.axvspan(5.2, 10, color="#FBEEEA", zorder=0)
    ax.axvline(4.0, color=C_GREY, ls="--", lw=1.3)
    ax.text(2.0, 2.55, "欠拟合\n高偏差", ha="center", fontsize=13, color=C_GREY)
    ax.text(4.1, 2.55, "合适", ha="center", fontsize=13, color=C_MAIN, fontweight="bold")
    ax.text(7.6, 2.55, "过拟合\n高方差", ha="center", fontsize=13, color=C_ACC)
    ax.annotate("两线差距 = 泛化差距", xy=(7.8, 1.15), xytext=(6.0, 0.55),
                fontsize=11, color=C_GREY,
                arrowprops=dict(arrowstyle="-|>", color=C_GREY, lw=1.2))
    ax.set_xlabel("模型复杂度 / 训练轮数", fontsize=12, color="#333")
    ax.set_ylabel("误差", fontsize=12, color="#333")
    ax.set_ylim(0, 2.9); ax.set_xlim(1, 10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=12, frameon=False, loc="upper center", ncol=2)
    ax.tick_params(labelsize=10, colors="#555")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


# ---------- 3 XOR ----------

def fig_xor(path):
    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    pts = [(0, 0), (0, 1), (1, 0), (1, 1)]
    for (px, py) in pts:
        c = C_ACC if px != py else C_MAIN
        ax.scatter(px, py, s=520, c=c, zorder=3, edgecolors="white", linewidths=2.5)
        ax.text(px, py - 0.16, str(int(px != py)), ha="center", fontsize=12,
                color="white", fontweight="bold", zorder=4)
    xs = np.linspace(-0.6, 1.6, 10)
    ax.plot(xs, 0.62 - xs, color=C_GREY, lw=2.0, ls="--")
    ax.text(0.06, 1.33, "任何一条直线都分不开这两类", fontsize=11.5, color=C_ACC,
            ha="left", va="center")
    ax.annotate("", xy=(1.55, -0.5), xytext=(0.55, 0.5),
                arrowprops=dict(arrowstyle="-|>", color=C_ACC, lw=2.2))
    ax.set_xlim(-0.6, 1.7); ax.set_ylim(-0.6, 1.5)
    ax.set_xlabel("$x_1$", fontsize=13); ax.set_ylabel("$x_2$", fontsize=13)
    ax.set_title("异或问题：线性模型的能力边界", fontsize=14, color=C_MAIN, pad=12)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=10, colors="#555")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


# ---------- 4 隐藏层折叠 ----------

def fig_xor_hidden(path):
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.6))
    pts = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], float)
    labels = np.array([0, 1, 1, 0])
    cols = [C_MAIN if l == 0 else C_ACC for l in labels]

    a = axes[0]
    a.scatter(pts[:, 0], pts[:, 1], s=420, c=cols, zorder=3,
              edgecolors="white", linewidths=2.2)
    xs = np.linspace(-0.5, 1.5, 10)
    a.plot(xs, 0.62 - xs, color=C_GREY, lw=2, ls="--")
    a.set_title("原始空间：线性不可分", fontsize=13, color=C_GREY, pad=10)
    a.set_xlim(-0.5, 1.5); a.set_ylim(-0.5, 1.5)
    a.set_xlabel("$x_1$", fontsize=12); a.set_ylabel("$x_2$", fontsize=12)

    b = axes[1]
    t = np.array([[0.2, 0.1], [1.9, 0.0], [0.1, 1.9], [1.6, 1.6]])
    b.scatter(t[:, 0], t[:, 1], s=420, c=cols, zorder=3,
              edgecolors="white", linewidths=2.2)
    xs2 = np.linspace(0, 2, 50)
    b.plot(xs2, 1.0 - 0.05 * xs2, color=C_MAIN, lw=2.2)
    b.set_title("隐藏层变换后：一条直线分开", fontsize=13, color=C_MAIN, pad=10)
    b.set_xlim(-0.3, 2.2); b.set_ylim(-0.3, 2.2)
    b.set_xlabel("$h_1$", fontsize=12); b.set_ylabel("$h_2$", fontsize=12)

    for a_ in axes:
        for s in ("top", "right"):
            a_.spines[s].set_visible(False)
        a_.tick_params(labelsize=9, colors="#555")
    fig.text(0.5, -0.02, "隐藏层的作用：把输入搬到另一个坐标系，让原本纠缠的两类变得可切",
             ha="center", fontsize=12, color="#555")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


# ---------- 5 张量形状 ----------

def fig_tensor_shape(path):
    fig, ax = plt.subplots(figsize=(10.6, 4.4))
    ax.set_xlim(0, 11.2); ax.set_ylim(0, 4.4); _clean(ax)
    stages = [
        ("输入\n32×1×28×28", 1.15),
        ("卷积 6@5×5\n32×6×28×28", 3.1),
        ("池化 2×2\n32×6×14×14", 5.05),
        ("卷积 16@5×5\n32×16×10×10", 7.0),
        ("展平\n32×1600", 8.55),
        ("全连接\n32×10", 10.0),
    ]
    for i, (txt, cx) in enumerate(stages):
        h = 1.05 + 0.12 * min(i, 3)
        _box(ax, cx, 2.5, 1.55, h, txt, fs=10.5,
             fc=C_LIGHT if i < 4 else "#FDF3E3",
             ec=C_MAIN if i < 4 else C_ORANGE,
             tc=C_MAIN if i < 4 else "#B87322")
        if i:
            _arrow(ax, (stages[i - 1][1] + 0.82, 2.5), (cx - 0.82, 2.5), lw=1.4)
    ax.text(5.3, 0.85, "批量维 32 全程不变；空间尺寸逐层缩小，通道数逐层变大——这就是 CNN 的「先宽后窄」",
            ha="center", fontsize=11.5, color="#555")
    ax.text(5.3, 3.95, "一次前向传播：每一层都在改形状", ha="center", fontsize=14,
            color=C_MAIN, fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


# ---------- 6 反向传播 ----------

def fig_backprop(path):
    fig, ax = plt.subplots(figsize=(10.4, 4.6))
    ax.set_xlim(0, 10.4); ax.set_ylim(0, 4.6); _clean(ax)
    nodes = [(1.0, 2.3, "x"), (3.0, 2.3, "z¹=W¹x+b¹"),
             (4.9, 2.3, "h=σ(z¹)"), (6.8, 2.3, "z²=W²h+b²"),
             (8.6, 2.3, "L")]
    for (x, y, t) in nodes:
        _box(ax, x, y, 1.5, 1.0, t, fs=11)
    for i in range(len(nodes) - 1):
        _arrow(ax, (nodes[i][0] + 0.78, 2.3), (nodes[i + 1][0] - 0.78, 2.3))
    # 反向箭头
    grads = [r"$\partial L/\partial h$", r"$\partial L/\partial z^1$", r"$\partial L/\partial x$"]
    for i in range(len(nodes) - 2, -1, -1):
        x1 = nodes[i + 1][0] - 0.3
        x2 = nodes[i][0] + 0.3
        _arrow(ax, (x1, 1.45), (x2, 1.45), color=C_ACC, lw=1.6)
    for i, g in enumerate(grads):
        xm = (nodes[i + 1][0] + nodes[i][0]) / 2
        ax.text(xm, 1.12, g, ha="center", fontsize=9.5, color=C_ACC)
    ax.text(5.2, 3.35, "前向：算值并缓存中间结果", ha="center", fontsize=12.5,
            color=C_MAIN, fontweight="bold")
    ax.text(5.2, 0.62, "反向：从 L 往回乘局部导数，一次拿到全部参数的梯度",
            ha="center", fontsize=12.5, color=C_ACC, fontweight="bold")
    ax.text(5.2, 0.22, "关键：∂L/∂W¹ = (∂L/∂z¹) · (∂z¹/∂W¹)，中间量复用，所以只需一次反向遍历",
            ha="center", fontsize=10.5, color="#666")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


# ---------- 7 梯度消失 ----------

def fig_grad_vanishing(path):
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.2))
    a = axes[0]
    x = np.linspace(-6, 6, 400)
    s = 1 / (1 + np.exp(-x))
    a.plot(x, s, color=C_MAIN, lw=2.4, label="σ(x)")
    a.plot(x, s * (1 - s), color=C_ACC, lw=2.4, label="σ′(x)")
    a.axhline(0.25, color=C_GREY, ls="--", lw=1.2)
    a.text(2.2, 0.285, "上界 0.25", fontsize=10.5, color=C_GREY)
    a.set_title("sigmoid 的导数最大只有 0.25", fontsize=12.5, color=C_MAIN, pad=10)
    a.legend(fontsize=10.5, frameon=False)
    a.set_xlabel("x"); a.tick_params(labelsize=9, colors="#555")

    b = axes[1]
    n = np.arange(1, 13)
    for base, c, lab in ((0.25, C_ACC, "sigmoid（×0.25）"), (0.9, C_MAIN, "ReLU 健康区（×0.9）")):
        b.semilogy(n, base ** n, "o-", color=c, lw=2.0, ms=5, label=lab)
    b.axhline(1e-4, color=C_GREY, ls=":", lw=1.2)
    b.text(1.2, 1.4e-4, "梯度信号低于此值，浅层等于没学", fontsize=9.8, color=C_GREY)
    b.set_title("12 层连乘后：梯度衰减到什么量级", fontsize=12.5, color=C_MAIN, pad=10)
    b.set_xlabel("层数（从输出往回数）"); b.set_ylabel("梯度相对大小")
    b.legend(fontsize=10, frameon=False)
    b.tick_params(labelsize=9, colors="#555")
    for a_ in axes:
        for sp in ("top", "right"):
            a_.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


# ---------- 8 loss 曲线诊断 ----------

def fig_loss_curve(path):
    fig, axes = plt.subplots(2, 2, figsize=(10.4, 6.2))
    ep = np.arange(0, 40)
    rng = np.random.default_rng(7)

    cases = [
        ("健康：两条都在降，差距稳定", C_MAIN, None),
        ("学习率过大：震荡甚至发散", C_ACC, "spike"),
        ("学习率过小：降得慢，像卡住", C_GREY, "slow"),
        ("过拟合：训练降、验证升", C_ORANGE, "over"),
    ]
    for ax, (title, col, kind) in zip(axes.ravel(), cases):
        if kind is None:
            tr = 0.9 * np.exp(-ep / 9) + 0.12
            va = 1.0 * np.exp(-ep / 10) + 0.22
            ax.plot(ep, tr, color=C_MAIN, lw=2.0, label="训练")
            ax.plot(ep, va, color=C_ACC, lw=2.0, label="验证")
        elif kind == "spike":
            tr = 0.9 * np.exp(-ep / 9) + 0.15 + 0.28 * np.abs(np.sin(ep * 1.15)) * np.exp(-ep / 60)
            ax.plot(ep, tr, color=C_ACC, lw=1.8)
            ax.set_ylim(0, 1.6)
            ax.text(14, 1.35, "来回横跳，不下降", fontsize=10, color=C_ACC)
        elif kind == "slow":
            tr = 0.95 * np.exp(-ep / 45) + 0.05
            ax.plot(ep, tr, color=C_GREY, lw=2.0)
            ax.set_ylim(0, 1.15)
            ax.text(12, 0.95, "斜率几乎为零", fontsize=10, color=C_GREY)
        else:
            tr = 0.9 * np.exp(-ep / 6) + 0.06
            va = 0.85 * np.exp(-ep / 7) + 0.05 + 0.016 * ep
            ax.plot(ep, tr, color=C_MAIN, lw=2.0, label="训练")
            ax.plot(ep, va, color=C_ORANGE, lw=2.0, label="验证")
            ax.axvline(14, color=C_GREY, ls="--", lw=1.2)
            ax.text(15, 0.85, "该停", fontsize=10, color=C_GREY)
            ax.set_ylim(0, 1.15)
        ax.set_title(title, fontsize=11.5, color=col, pad=8)
        ax.tick_params(labelsize=8.5, colors="#555")
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.set_xlabel("轮数", fontsize=9.5); ax.set_ylabel("损失", fontsize=9.5)
    axes[0][0].legend(fontsize=9, frameon=False)
    axes[1][1].legend(fontsize=9, frameon=False)
    fig.suptitle("四种 loss 曲线，对应四种改法", fontsize=13.5, color=C_MAIN, y=1.0)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


# ---------- 9 卷积与参数共享 ----------

def fig_conv(path):
    fig, ax = plt.subplots(figsize=(9.2, 5.0))
    ax.set_xlim(0, 9.2); ax.set_ylim(0, 5.0); _clean(ax)
    cell = 0.52
    ox, oy = 0.7, 1.35
    rng = np.random.default_rng(3)
    vals = rng.integers(0, 6, size=(5, 5))
    for i in range(5):
        for j in range(5):
            shaded = (1 <= i <= 3) and (1 <= j <= 3)
            ax.add_patch(Rectangle((ox + j * cell, oy + (4 - i) * cell), cell, cell,
                                   fc="#FBEEEA" if shaded else "#F4F7FB",
                                   ec=C_ACC if shaded else C_GREY, lw=1.4 if shaded else 0.8))
            ax.text(ox + j * cell + cell / 2, oy + (4 - i) * cell + cell / 2,
                    str(vals[i, j]), ha="center", va="center", fontsize=9.5,
                    color=C_ACC if shaded else "#666")
    ax.add_patch(Rectangle((ox + 1 * cell, oy + 1 * cell), 3 * cell, 3 * cell,
                           fill=False, ec=C_ACC, lw=2.6))
    ax.text(ox + 2.5 * cell, oy - 0.32, "输入 5×5", ha="center", fontsize=11.5, color="#444")

    # 卷积核
    kx, ky = 3.85, 2.55
    for i in range(3):
        for j in range(3):
            ax.add_patch(Rectangle((kx + j * cell, ky + (2 - i) * cell), cell, cell,
                                   fc="#FDF3E3", ec=C_ORANGE, lw=1.2))
            ax.text(kx + j * cell + cell / 2, ky + (2 - i) * cell + cell / 2,
                    "w", ha="center", va="center", fontsize=9.5, color="#B87322")
    ax.text(kx + 1.5 * cell, ky - 0.32, "同一组权重\n滑过整张图", ha="center", fontsize=11,
            color="#B87322")
    _arrow(ax, (ox + 1.0 + 3 * cell + 0.05, oy + 2.5 * cell), (kx - 0.12, oy + 2.5 * cell),
           lw=1.8)

    # 输出
    gx = 6.6
    for i in range(3):
        for j in range(3):
            ax.add_patch(Rectangle((gx + j * cell, oy + 2.0 + (2 - i) * cell), cell, cell,
                                   fc=C_LIGHT, ec=C_MAIN, lw=1.0))
    ax.text(gx + 1.5 * cell, oy - 0.32, "特征图 3×3", ha="center", fontsize=11.5, color=C_MAIN)
    _arrow(ax, (kx + 3 * cell + 0.08, oy + 2.5 * cell), (gx - 0.12, oy + 2.5 * cell), lw=1.8)

    ax.text(4.6, 4.55, "卷积：局部连接 + 参数共享", ha="center", fontsize=14.5,
            color=C_MAIN, fontweight="bold")
    ax.text(4.6, 0.45, "5×5 全连接要 25 个权重；3×3 卷积只要 9 个，且在图里任何位置都复用同一组",
            ha="center", fontsize=10.8, color="#666")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


# ---------- 10 残差块 ----------

def fig_resnet(path):
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.6))
    for ax, title, residual in ((axes[0], "普通块：直接拟合 H(x)", False),
                                (axes[1], "残差块：只拟合 F(x)=H(x)−x", True)):
        ax.set_xlim(0, 5); ax.set_ylim(0, 6); _clean(ax)
        _box(ax, 2.5, 5.3, 1.9, 0.72, "输入 x", fc="#F4F7FB", fs=11)
        _box(ax, 2.5, 3.9, 1.9, 0.72, "权重层 + 激活", fs=11)
        _box(ax, 2.5, 2.5, 1.9, 0.72, "权重层 + 激活", fs=11)
        _box(ax, 2.5, 1.2, 1.9, 0.72, "输出", fc="#FDF3E3", ec=C_ORANGE, tc="#B87322", fs=11)
        _arrow(ax, (2.5, 4.94), (2.5, 4.28))
        _arrow(ax, (2.5, 3.54), (2.5, 2.88))
        if residual:
            _arrow(ax, (2.5, 2.14), (2.5, 1.58))
            ax.add_patch(FancyArrowPatch((3.45, 5.3), (3.45, 1.2), arrowstyle="-|>",
                                         color=C_ACC, lw=2.2, mutation_scale=16,
                                         connectionstyle="arc3,rad=-0.42"))
            ax.text(4.35, 3.2, "+x\n恒等通路", fontsize=10.5, color=C_ACC,
                    ha="center", va="center")
            ax.add_patch(Circle((3.45, 1.2), 0.13, fc="white", ec=C_ACC, lw=1.8, zorder=5))
            ax.text(3.45, 1.2, "+", ha="center", va="center", fontsize=11,
                    color=C_ACC, fontweight="bold", zorder=6)
        else:
            _arrow(ax, (2.5, 2.14), (2.5, 1.58))
        ax.set_title(title, fontsize=12, color=C_MAIN if not residual else C_ACC, pad=8)
    fig.text(0.5, 0.015,
             "深层网络的困境：让一堆层学「恒等映射」很难；让它学「零」，也就是什么都不改，容易得多",
             ha="center", fontsize=10.6, color="#666")
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


# ---------- 11 过拟合直觉（D 版用） ----------

def fig_overfit_intuition(path):
    """背题 vs 会做题。

    红线的「抖动」用可控的叠加正弦造，不用高阶多项式：多项式在数据范围外会指数发散，
    裁到 ylim 里就成了一条贴边的水平线，比不画还糟。
    """
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    rng = np.random.default_rng(11)
    x = np.sort(rng.uniform(0.8, 9.2, 13))
    true_y = np.sin(x * 0.6) * 2
    y = true_y + rng.normal(0, 0.32, x.size)
    xs = np.linspace(0.5, 9.5, 500)
    ax.scatter(x, y, s=72, c=C_MAIN, zorder=5, edgecolors="white", linewidths=1.6,
               label="已知的样例")
    ax.plot(xs, np.sin(xs * 0.6) * 2, color=C_MAIN, lw=2.4, label="真正的规律")
    wiggle = np.sin(xs * 0.6) * 2 + 0.62 * np.sin(xs * 3.6 + 0.7) \
        + 0.28 * np.sin(xs * 6.9)
    ax.plot(xs, wiggle, color=C_ACC, lw=1.9, label="死记硬背（跟着每个点走）")
    ax.set_ylim(-4.0, 4.6); ax.set_xlim(0, 10)
    ax.set_xticks([]); ax.set_yticks([])
    ax.legend(fontsize=10.5, frameon=False, loc="upper left", ncol=1)
    ax.text(5, -3.55, "红线把每个样例都记住了，但新样例一来就错——这就是过拟合",
            ha="center", fontsize=11, color=C_ACC)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


# ---------- 12 人工神经元模型 ----------

def fig_neuron(path):
    """人工神经元的数学模型：加权求和、减去阈值、过激活函数。"""
    fig, ax = plt.subplots(figsize=(9.6, 4.2))
    ax.set_xlim(0, 10); ax.set_ylim(0, 4.2); _clean(ax)

    ys = [3.15, 2.45, 1.75]
    labels = ["$x_1$", "$x_2$", "$x_3$"]
    ws = ["$w_1$", "$w_2$", "$w_3$"]
    for y, lb, wl in zip(ys, labels, ws):
        ax.add_patch(Circle((1.0, y), 0.26, fc=C_LIGHT, ec=C_MAIN, lw=1.6))
        ax.text(1.0, y, lb, ha="center", va="center", fontsize=14, color=C_MAIN)
        _arrow(ax, (1.30, y), (3.35, 2.45), color=C_GREY, lw=1.3)
        ax.text(2.25, y + 0.14 if y > 2.45 else y + 0.16, wl, fontsize=13,
                color=C_ACC, ha="center")

    ax.add_patch(Circle((3.75, 2.45), 0.42, fc="#FBEEEA", ec=C_ACC, lw=1.8))
    ax.text(3.75, 2.45, "Σ", ha="center", va="center", fontsize=20, color=C_ACC)

    # 阈值 θ（教师写法：减 θ，等价于加偏置 b=-θ）
    _box(ax, 3.75, 1.05, 1.5, 0.6, "阈值 $\\theta$", fc="#FDF3E3", ec=C_ORANGE,
         fs=12, tc="#B87322")
    _arrow(ax, (3.75, 1.38), (3.75, 2.0), color=C_ORANGE, lw=1.4)
    ax.text(4.35, 1.05, "（等价于偏置 $b=-\\theta$）", fontsize=10.5, color=C_GREY,
            va="center", ha="left")

    _box(ax, 5.75, 2.45, 1.7, 1.0, "激活函数\n$f(\\cdot)$", fc="#EDF3FA", ec=C_ALT,
         fs=13, tc=C_MAIN)
    _arrow(ax, (4.22, 2.45), (4.88, 2.45))
    _arrow(ax, (6.62, 2.45), (8.05, 2.45), color=C_MAIN, lw=1.9)
    ax.text(8.35, 2.45, "$y$", fontsize=17, color=C_MAIN, va="center", ha="left")

    ax.text(5.0, 0.28,
            "$y = f\\left(\\sum_{i} w_i x_i - \\theta\\right)$",
            ha="center", fontsize=16, color=C_MAIN)
    ax.text(1.0, 3.85, "输入", fontsize=11, color=C_GREY, ha="center")
    ax.text(3.75, 3.25, "加权求和", fontsize=11, color=C_ACC, ha="center")
    ax.text(5.75, 3.25, "非线性", fontsize=11, color=C_ALT, ha="center")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


# ---------- 13 前馈 vs 反馈 ----------

def fig_feedforward(path):
    """前馈是单向层叠，反馈有回路：一张图说清两者差别。"""
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.0))
    titles = ["前馈网络：信息单向流动", "反馈网络：输出回到输入"]
    for k, ax in enumerate(axes):
        ax.set_xlim(0, 5); ax.set_ylim(0, 4.2); _clean(ax)
        ax.set_title(titles[k], fontsize=13, color=C_MAIN, pad=10, fontweight="bold")
        cols = [(1.0, [3.0, 2.1, 1.2]), (2.5, [3.15, 2.1, 1.05]), (4.0, [2.6, 1.6])]
        for ci, (cx, ys) in enumerate(cols):
            for y in ys:
                ax.add_patch(Circle((cx, y), 0.19,
                                    fc=C_LIGHT if ci < 2 else "#FBEEEA",
                                    ec=C_MAIN if ci < 2 else C_ACC, lw=1.4))
        for ci in range(len(cols) - 1):
            x0, ys0 = cols[ci]
            x1, ys1 = cols[ci + 1]
            for y0 in ys0:
                for y1 in ys1:
                    _arrow(ax, (x0 + 0.20, y0), (x1 - 0.20, y1), color=C_GREY, lw=0.8)
        # 右图上方的回弧会压住任何标签，层级标注只在左图做一次，
        # 右图靠副标题和底部注记说明差异
        if k == 0:
            ax.text(1.0, 3.75, "输入层", fontsize=10.5, color=C_GREY, ha="center")
            ax.text(2.5, 3.85, "隐藏层", fontsize=10.5, color=C_GREY, ha="center")
            ax.text(4.0, 3.2, "输出层", fontsize=10.5, color=C_ACC, ha="center")
        if k == 1:
            _arrow(ax, (4.30, 3.05), (0.72, 3.55), color=C_ACC, lw=1.9, rad=0.40)
            ax.text(2.5, 0.45, "输出回灌，网络因此有记忆", fontsize=10.5,
                    color=C_ACC, ha="center")
        else:
            ax.text(2.5, 0.45, "同层不连、不跨层回连", fontsize=10.5,
                    color=C_GREY, ha="center")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)


FIGURES = {
    "ml-loop": fig_ml_loop,
    "bias-variance": fig_bias_variance,
    "xor": fig_xor,
    "xor-hidden": fig_xor_hidden,
    "tensor-shape": fig_tensor_shape,
    "backprop": fig_backprop,
    "grad-vanishing": fig_grad_vanishing,
    "loss-curve": fig_loss_curve,
    "conv": fig_conv,
    "resnet": fig_resnet,
    "overfit-intuition": fig_overfit_intuition,
    "neuron": fig_neuron,
    "feedforward": fig_feedforward,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="figs")
    ap.add_argument("--only", default="", help="逗号分隔的图名，留空则全部")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    names = [n.strip() for n in args.only.split(",") if n.strip()] or list(FIGURES)
    bad = [n for n in names if n not in FIGURES]
    if bad:
        sys.exit(f"未知图名：{bad}；可用：{list(FIGURES)}")
    made = []
    for n in names:
        p = os.path.join(args.out, f"fig_{n.replace('-', '_')}.png")
        FIGURES[n](p)
        made.append(p)
        print(f"  [ok] {p}")
    # 拼一张 contact 供人一眼看完
    try:
        from PIL import Image
        imgs = [Image.open(p) for p in made]
        cols = 3 if len(imgs) > 4 else 2
        rows = (len(imgs) + cols - 1) // cols
        tw = 760
        thumbs = []
        for im in imgs:
            r = tw / im.width
            thumbs.append(im.resize((tw, int(im.height * r))))
        ch = max(t.height for t in thumbs)
        sheet = Image.new("RGB", (cols * tw + 20 * (cols + 1), rows * (ch + 20) + 20), "white")
        for i, t in enumerate(thumbs):
            r_, c_ = divmod(i, cols)
            sheet.paste(t, (20 + c_ * (tw + 20), 20 + r_ * (ch + 20)))
        cp = os.path.join(args.out, "contact.png")
        sheet.save(cp)
        print(f"  [contact] {cp}")
    except Exception as e:
        print(f"  [warn] contact 生成跳过：{e}")
    print(f"完成 {len(made)} 张 → {args.out}")


if __name__ == "__main__":
    main()
