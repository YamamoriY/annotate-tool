# annotate-tool

COCO instance-segmentation アノテーションのビューア(PySide6)。
丸太の木口(log end faces)のセグメンテーション結果を画像に重ねて確認するためのツール。

## 起動

```sh
uv run src/main.py [path/to/instances.json]
# または(uv sync 後)
uv run annotate-tool [path/to/instances.json]
```

引数を省略すると `data/instances.json` を読み込む。画像は JSON と同じディレクトリから
`file_name` で解決される。

## 操作

| 操作 | キー / マウス |
| --- | --- |
| 前 / 次の画像 | ← / → (D, Space) |
| 画面にフィット | F |
| オーバーレイ表示切替 | V |
| 塗りつぶし切替 | B |
| 選択解除 | Esc |
| ズーム | ホイール |
| パン | 中ボタンドラッグ |
| インスタンス選択 | ポリゴンをクリック、または左の一覧をクリック |
| 複数選択(追加 / 解除) | Shift + クリック |
| 矩形選択 | 左ドラッグ(矩形に触れたインスタンスを選択へ追加) |
| 選択インスタンスを削除 | Delete(または上部の「削除」ボタン) |
| インスタンス追加(開始) | A(または上部の「追加」ボタン。未選択のときだけ) |
| 追加モードで塗る | 左ドラッグ(塗りつぶしペン) |
| 追加を確定 | Enter(または塗り始めると出る「確定」ボタン) |
| 追加を取消 | Esc(または追加中に出る「キャンセル」ボタン) |

## 構成

```
src/annotate_tool/
├── app.py            # エントリポイント(引数解析・起動)
├── coco_data.py      # GUI 非依存の COCO データモデル / IO
├── state.py          # ViewerState: アプリ状態の一元管理(single source of truth)
├── style.py          # 色・スタイル・レイアウト定数
└── widgets/
    ├── main_window.py     # 組み立てと配線のみ(composition root)
    ├── image_view.py      # 画像 + ポリゴン描画ビュー
    ├── instance_panel.py  # インスタンス一覧ドック(左)
    ├── side_panel.py      # 操作パネル・ドック(右)
    ├── control_group.py   # 見出し付きボタングループ(移動 / 表示)
    ├── action_bar.py      # 浮動アクションバー(選択解除 / 削除)
    └── add_bar.py         # 浮動バー(追加 / キャンセル / 確定)。塗りつぶしで新規追加
```

設計方針:

- 状態(現在画像・選択・表示フラグ)は `ViewerState` だけが持つ。
  ウィジェットは操作を `ViewerState` のメソッド呼び出しに変換し、
  表示更新はシグナル経由で受け取る。
- `coco_data.py` は Qt に依存しないため、将来の編集・保存機能や
  CLI ツールからもそのまま使える。
- 見た目の定数は `style.py` に集約。

## テスト

```sh
uv run pytest
```
