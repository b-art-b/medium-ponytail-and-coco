"""Render the article figures from results/summary.json.

matplotlib is not a benchmark dependency, so run this from a throwaway environment:
  uv venv /tmp/ponytail-figures && uv pip install --python /tmp/ponytail-figures/bin/python 'matplotlib==3.10.*'
  /tmp/ponytail-figures/bin/python git/runner/figures.py
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'images'
FONT = Path.home() / 'Library/Fonts/Excalifont-Regular.ttf'
PINK, GREEN, BLUE, YELLOW = '#f4a6a6', '#8fdc9c', '#8cc8f5', '#f7dc6f'
ARMS = (('A', 'Stock CoCo', PINK), ('B', 'Lean baseline', GREEN), ('C', 'Baseline + Ponytail', YELLOW))


def setup():
    if FONT.exists():
        font_manager.fontManager.addfont(str(FONT))
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=FONT).get_name()
    plt.rcParams['hatch.linewidth'] = 1.2
    plt.rcParams['path.sketch'] = (1.2, 120, 2)


# (fill, border, text) per tone: soft solid fill, deeper border, dark text of the same hue
TONES = {
    'pink': ('#fde4e4', '#e07a7a', '#7a2e2e'),
    'green': ('#e1f6e4', '#5fb873', '#245c33'),
    'blue': ('#e0f0fc', '#5aa3d8', '#1f4e75'),
    'yellow': ('#fdf3d2', '#e0b93a', '#6b5310'),
    'grey': ('#f1f1f4', '#9a9aa6', '#3c3c46'),
}
LINE = '#8a8a96'


def card(ax, x, y, w, h, title, body, tone, size=17):
    fill, edge, ink = TONES[tone]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0,rounding_size=0.25',
                                facecolor=fill, edgecolor=edge, linewidth=2.4))
    cx = x + w / 2
    if body:
        ax.text(cx, y + h * 0.68, title, ha='center', va='center', fontsize=size, color=ink, fontweight='bold')
        ax.text(cx, y + h * 0.32, body, ha='center', va='center', fontsize=size - 4, color=ink,
                alpha=0.85, linespacing=1.4)
    else:
        ax.text(cx, y + h / 2, title, ha='center', va='center', fontsize=size, color=ink, fontweight='bold')


def arrow(ax, start, end, style='-|>'):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle=style, mutation_scale=20, linewidth=2,
                                 color=LINE, connectionstyle='arc3,rad=0', shrinkA=2, shrinkB=2))


def architecture():
    fig, ax = plt.subplots(figsize=(16, 10), dpi=150)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis('off')

    tops = (('Arm A: stock CoCo', 'no extra instructions', 'pink'),
            ('Arm B: lean baseline', 'AGENTS.md + lean-build,\nsurgical-patch, verify-and-stop', 'green'),
            ('Arm C: B + Ponytail', 'baseline + Ponytail SKILL.md', 'yellow'))
    for i, (title, body, tone) in enumerate(tops):
        card(ax, 0.4 + i * 5.2, 8.0, 4.8, 1.7, title, body, tone)
        arrow(ax, (2.8 + i * 5.2, 8.0), (6.0 + i * 2.0, 7.05))

    card(ax, 3.6, 5.4, 8.8, 1.6, 'CoCo CLI, headless',
         'claude-opus-5-5, isolated settings\n8 tasks x 3 arms x 3 reps = 72 runs', 'blue')
    card(ax, 13.0, 5.4, 2.8, 1.6, 'Guard plugin', 'PreToolUse hook\npaths, protected files', 'grey', 15)
    arrow(ax, (13.0, 6.2), (12.4, 6.2))

    arrow(ax, (8.0, 5.4), (8.0, 4.7))
    card(ax, 3.6, 3.4, 8.8, 1.3, 'Fresh project copy per run', 'the agent edits only this copy', 'green')

    arrow(ax, (6.2, 3.4), (4.0, 2.65))
    arrow(ax, (9.8, 3.4), (12.0, 2.65))
    card(ax, 0.4, 1.0, 7.0, 1.6, 'Docker sandbox', 'no network, read-only\npytest + Streamlit AppTest', 'yellow')
    card(ax, 8.6, 1.0, 7.0, 1.6, 'Snowflake, scoped user',
         'one schema per run\nDynamic Tables, dbt + hidden rows', 'blue')

    ax.text(8.0, 0.35, 'Measured: pass/fail  ·  time  ·  tokens  ·  lines changed',
            ha='center', fontsize=15, color=TONES['grey'][2])

    fig.savefig(OUT / 'architecture.png', bbox_inches='tight', facecolor='white')
    plt.close(fig)


ARM_TONES = ('pink', 'green', 'yellow')


def bar_chart(summary, key, title, subtitle, fmt, filename):
    arms = summary['arms']
    values = [arms[arm][key] for arm, _, _ in ARMS]
    labels = [label for _, label, _ in ARMS]
    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=150)
    rows = range(len(values))[::-1]
    for row, value, tone in zip(rows, values, ARM_TONES):
        fill, edge, ink = TONES[tone]
        ax.barh(row, value, height=0.62, color=fill, edgecolor=edge, linewidth=2.4)
        ax.text(value + max(values) * 0.02, row, fmt.format(value), va='center', fontsize=17,
                color=ink, fontweight='bold')
    ax.set_yticks(list(rows), labels, fontsize=15, color=TONES['grey'][2])
    ax.tick_params(axis='y', length=0, pad=10)
    ax.set_xlim(0, max(values) * 1.2)
    ax.set_xticks([])
    for side in ('top', 'right', 'bottom'):
        ax.spines[side].set_visible(False)
    ax.spines['left'].set_color(LINE)
    ax.spines['left'].set_linewidth(2)
    ax.set_title(title, fontsize=20, color=TONES['grey'][2], loc='left', pad=34, fontweight='bold')
    ax.text(0, 1.04, subtitle, transform=ax.transAxes, fontsize=14, color=LINE, ha='left')
    fig.savefig(OUT / filename, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def results(summary):
    bar_chart(summary, 'total_output_tokens', 'Total output tokens',
              'all 72 runs  ·  lower is better', '{:,.0f}', 'results-tokens.png')
    bar_chart(summary, 'median_test_added_passed', 'Median test lines added',
              'passing runs  ·  lower is better (production lines: 4 in every arm)', '{:g}',
              'results-tests.png')


def main():
    setup()
    OUT.mkdir(exist_ok=True)
    architecture()
    results(json.loads((ROOT / 'results' / 'summary.json').read_text()))


if __name__ == '__main__':
    main()
