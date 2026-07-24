# パッケージング

## Windows

```powershell
.\packaging\build-windows.ps1
```

アイコン生成 → PyInstaller (onedir) → Inno Setup まで走る。

| コマンド | 出力 |
| --- | --- |
| `build-windows.ps1` | `dist\win\annotate-tool-setup-<version>.exe` |
| `build-windows.ps1 -NoInstaller` | `dist\win\annotate-tool\` のみ |
| `build-windows.ps1 -OneFile` | `dist\win\annotate-tool-onefile.exe` |

インストーラーには Inno Setup が要る。未インストールなら onedir まで作って警告を出す。

```powershell
winget install --id JRSoftware.InnoSetup -e
```

## macOS

```sh
./packaging/build-macos.sh              # dist/mac/annotate-tool.app
./packaging/build-macos.sh --onefile    # dist/mac/annotate-tool-onefile
```

`.app` は実体がディレクトリなので、配布するときは zip する。Finder の「圧縮」でなく
`ditto` を使うのは、symlink とパーミッションを保つため。

```sh
cd dist/mac && ditto -c -k --keepParent annotate-tool.app annotate-tool-mac.zip
```

ビルドしたマシンの CPU アーキテクチャ専用バイナリになる(PySide6 が universal2 wheel を
出していないため universal 化は不可)。クロスコンパイルもできないので、macOS 版は Mac 実機で
ビルドする。

## リリース

GitHub CLI でログインしてから、リリースする OS 上で実行する。
ビルド、zip 作成、GitHub Releases への公開まで一度に行う。

```powershell
# Windows
.\packaging\release-windows.ps1
```

```sh
# macOS
bash packaging/release-mac.sh
```

`pyproject.toml` の `version` からタグ名 (`v<version>`) と成果物名を決める。
そのタグのリリースがなければ自動生成したリリースノートで作成し、すでにあれば
該当 OS の成果物を追加する。同名の成果物は置き換えるので再実行できる。

Windows 版は installer と portable zip の両方を公開するため、Inno Setup が必要。

## 署名

Windows / macOS とも未署名。
