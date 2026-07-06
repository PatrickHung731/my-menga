# -*- coding: utf-8 -*-
"""頁面版型計算 — generate_panels(算每格長寬比) 與 compose_pages(算像素位置) 共用。

漫畫閱讀順序為「由右至左」：layout 每列的第一個 panel id 排在最右邊。
"""

MARGIN = 40      # 頁面外框留白
GUTTER_X = 24    # 同列格與格的水平間隔
GUTTER_Y = 34    # 列與列的垂直間隔


def page_cells(page, page_w, page_h):
    """回傳 {panel_id: (x, y, w, h)}，座標為頁面像素。

    page["layout"] 例: [[1], [2, 3], [4]] → 三列，中列兩格。
    page["row_weights"] 例: [1.2, 1, 0.8] → 各列相對高度，可省略。
    """
    layout = page["layout"]
    weights = page.get("row_weights") or [1] * len(layout)
    if len(weights) != len(layout):
        raise ValueError("row_weights 長度需等於 layout 列數")

    inner_w = page_w - 2 * MARGIN
    inner_h = page_h - 2 * MARGIN - GUTTER_Y * (len(layout) - 1)
    total = float(sum(weights))

    cells = {}
    y = float(MARGIN)
    for row, wt in zip(layout, weights):
        rh = inner_h * wt / total
        n = len(row)
        cw = (inner_w - GUTTER_X * (n - 1)) / float(n)
        for i, pid in enumerate(row):
            # 由右至左排列
            x = MARGIN + inner_w - (i + 1) * cw - i * GUTTER_X
            cells[pid] = (int(round(x)), int(round(y)), int(round(cw)), int(round(rh)))
        y += rh + GUTTER_Y
    return cells
