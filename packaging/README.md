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

ビルド成果物は GitHub Releases に。
`pyproject.toml` の `version` に合わせたタグで作成する。

```powershell
gh release create v0.1.0 dist\win\annotate-tool-setup-0.1.0.exe `
  --title "v0.1.0" --notes "Windows 版 初回リリース"
```

`--draft` で非公開。
既存リリースへの追加は `gh release upload v0.1.0 <file>`。

## 署名

Windows / macOS とも未署名。
