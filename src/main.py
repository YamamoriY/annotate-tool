"""従来の起動方法 `uv run src/main.py` との互換用シム。

実体は annotate_tool パッケージ側にある。`uv run annotate-tool` でも起動できる。
"""

from annotate_tool.app import main

if __name__ == "__main__":
    main()
