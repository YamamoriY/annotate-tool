"""COCO instance-segmentation アノテーションの閲覧・編集ツール。

レイヤ構成:
    coco_data  -- GUI 非依存のデータモデル / IO
    state      -- アプリケーション状態(現在画像・選択・表示フラグ)の一元管理
    style      -- 色・スタイル・レイアウト定数
    widgets    -- Qt ウィジェット群(表示専用。状態は持たず state に従う)
    app        -- エントリポイント
"""

__version__ = "0.1.0"
