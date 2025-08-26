#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# 2025-07-19 '・' (\u30fb)を無視するように修正。
# 2025-07-18 Gemini 2.5pro で作成。

import argparse
import sys
import os
import shutil
import re
import uuid

def slugify(text: str) -> str:
    """
    見出しテキストからDocusaurus互換のアンカー文字列を生成します。
    ユーザー指定のルールに基づいています。
    1. 英大文字は小文字に変換
    2. 半角スペースはハイフン '-' に変換
    3. 半角記号は '_' 以外無視
    4. 全角空白・記号は '＿' 以外無視
    """
    slug = ""
    # Rule 1: 英大文字は小文字に変換
    text_lower = text.lower()

    for char in text_lower:
        # '・'(\u30fb)を無視するように修正
        # 日本語 (漢字、ひらがな、カタカナ), 英小文字, 数字
        if ('\u4e00' <= char <= '\u9fff' or  # 漢字
            '\u3040' <= char <= '\u309f' or  # ひらがな
            '\u30a0' <= char <= '\u30fa' or  # カタカナ
            'a' <= char <= 'z' or
            '0' <= char <= '9'):
            slug += char
        # Rule 2: 半角スペース -> ハイフン
        elif char == ' ':
            slug += '-'
        # Rule 3 & 4: 許可された記号
        elif char in ['_', '-',  '＿', 'ー']:
            slug += char
        # その他の文字は無視

    return slug

def remove_existing_toc(content: str) -> str:
    """
    ファイル内の既存の "## 目次" ブロックを削除します。
    """
    # '## 目次'から始まり、次の'## '見出しが現れる直前まで、またはファイル末尾までを非貪欲にマッチ
    # re.DOTALL: '.'が改行にもマッチするようにする
    # re.MULTILINE: '^'が各行の先頭にマッチするようにする

    pattern = re.compile(
        r'^##\s*目次\s*\n'
        r'(?:.*\n)*?'
        r'<!-- end of autogen index -->\s*\n?',  # 3. 終端コメント行（空白・改行許容）
        re.MULTILINE
    )
    # pattern = re.compile(r'^##\s+目次\s*$.*?(?=^##\s+|$)', re.DOTALL | re.MULTILINE)

    new_content, num_replacements = re.subn(pattern, '', content)

    # 目次ブロックの後に余分な空行が残る場合があるので、それを調整
    if num_replacements > 0:
        new_content = new_content.lstrip('\n')

    return new_content

def process_file(filepath: str, max_level: int):
    """
    単一のMarkdownファイルを処理して目次を生成・挿入します。
    """
    print(f"--- Processing {filepath} ---")

    # 1. level 0 の場合は処理をスキップ
    if max_level == 0:
        print("Skipping TOC generation (--level 0).")
        return

    # 2. ファイルを読み込む
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except IOError as e:
        print(f"Error: Cannot read file {filepath}. {e}", file=sys.stderr)
        return

    # 3. "<!-- index here -->" がなければスキップ（バックアップも作成しない）
    if '<!-- index here -->' not in original_content:
        print("Skipping: Marker '<!-- index here -->' not found.")
        return

    # ★★★【修正点 1】マーカーを一時的なプレースホルダーに置き換えて保護
    placeholder = f"__TOC_PLACEHOLDER_{uuid.uuid4()}__"
    content_with_placeholder = original_content.replace('<!-- index here -->', placeholder, 1)

    # 4. バックアップを作成
    try:
        shutil.copy2(filepath, f"{filepath}_bk")
        print(f"Backup created: {filepath}_bk")
    except IOError as e:
        print(f"Error: Could not create backup for {filepath}. {e}", file=sys.stderr)
        return

    # 5. 既存の目次ブロックを削除（マーカーは保護されているので安全）
    content_without_toc = remove_existing_toc(content_with_placeholder)

    # 6. 見出しを抽出 (コードブロック内は無視)
    headers = []
    in_code_block = False
    for line in content_without_toc.split('\n'):
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
        if in_code_block:
            continue

        match = re.match(r'^(#{2,})\s+(.*)', line)
        if match:
            level = len(match.group(1))
            if level <= max_level:
                title = match.group(2).strip()
                headers.append({'level': level, 'title': title})

    toc_string = ""
    if headers:
        # 7. 目次(TOC)文字列を生成
        toc_lines = ["## 目次", ""]
        generated_slugs = set()

        for header in headers:
            base_slug = slugify(header['title'])
            slug = base_slug

            count = 0
            while slug in generated_slugs:
                count += 1
                slug = f"{base_slug}-{count}"
            generated_slugs.add(slug)

            indent = '    ' * (header['level'] - 2)
            escaped_title = header['title'].replace('>', '&gt;').replace('<', '&lt;')

            toc_lines.append(f"{indent}1. <a href=\"#{slug}\">{escaped_title}</a>")

        toc_string = '\n'.join(toc_lines) + '\n' + r'<!-- end of autogen index -->'
    else:
        print("No headers found to generate TOC. Marker will be removed.")

    # ★★★【修正点 2】プレースホルダーを生成した目次文字列で置換する
    final_content = content_without_toc.replace(placeholder, toc_string, 1)

    # 8. 更新した内容をファイルに書き込む
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_content)
        print("TOC successfully generated and inserted.")
    except IOError as e:
        print(f"Error: Could not write to file {filepath}. {e}", file=sys.stderr)

def main():
    """
    メイン関数：コマンドライン引数を処理し、各ファイルに対して処理を実行します。
    """
    parser = argparse.ArgumentParser(
        description="Markdownファイルから目次を自動生成し、指定の場所に挿入します。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        'files',
        nargs='+',
        help='処理対象のMarkdownファイル (ワイルドカード指定可, 例: *.md)'
    )
    parser.add_argument(
        '--level',
        type=int,
        default=3,
        help="目次に含める見出しの最大レベル。\n"
             "  --level 2: '##' まで (デフォルト)\n"
             "  --level 3: '###' まで\n"
             "  --level 0: 目次を生成しない"
    )

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    for filepath in args.files:
        if not os.path.isfile(filepath):
            print(f"Skipping: '{filepath}' is not a valid file.", file=sys.stderr)
            continue
        process_file(filepath, args.level)
        print("-" * 30)

if __name__ == '__main__':
    main()


# 以下は AI に作成依頼したときのプロンプト。
r"""

markdown ファイルに含まれる見出しから、目次を自動生成するツールを以下の仕様で作成して。



1. 概要

- 環境は Windows11 + Python3.x + Git-bash端末

- ここで使う markdown ファイルは Docusaurus で処理します。Docusaurus はシステム内部でサイドバーに目次を自動生成しますが、markdown 本文にはその目次を挿入してくれません。そこでこのツールで目次を生成し、markdwon 本文に埋め込むことにします。その際、<a id="a_name">A NAME</a> といった見出し用の場所を示すタグは Docusaurus が markdown ファイルの中の「見出し」から内部で勝手に自動生成していいます。そのため、このツールでそのタグを作成する必要はありません。





2. 詳細



- 見出しのレベルはデフォルトで 2 とする(--level 3 相当)。起動パラメータで "--level 4" と指定された場合、#### のレベルまで目次を生成。

- "--level 0" と指定された場合は目次を生成しない。

- コマンドラインで 入力 markdown ファイルを指定します。目次の自動生成が不要な場合以外（後述）は、一旦入力ファイルのコピー（拡張子が .md_bk）を作成します。複数の markdown ファイルが指定可能にします。



具体例：



./gen_index_md.py  a.md b.md c.md



の場合、 a.md_bk, b.md_bk, c.md_bk をバックアップとして生成します。既に a.md_bk が存在していたら上書きします。





git-bash から、



./gen_index_md.py  *.md



という指定も受けつけるようにします。



- 生成した見出しの挿入位置は 入力の markdown ファイルの中に



<!-- index here -->



と記載のある行に、挿入し、"<!-- index here -->" の行は削除する。もしも、



<!-- index here -->



の行が存在しなければ、目次の生成、挿入はしない。この場合、バックアップファイル（.md_bk）は生成しない。



- 入力 markdown ファイルの中に既に "## 目次" のブロックが存在する場合、たとえば



```

## 目次



1. <a href="#あれ">あれ</a>

1. <a href="#これ">これ</a>



## 要約



## 詳細



```

となっている場合、"## 目次" のブロック





```

## 目次



1. <a href="#あれ">あれ</a>

1. <a href="#これ">これ</a>



```

を予め削除してから新たに目次を生成する。





2. 見出しの文字列から、目次を生成するルール



- 半角記号は無視、ただし '_' だけはそのまま残す。

- 見出しに含まれる半角空白 ' ' は '-' に置き換える。

- 大文字の英文字は小文字に置き換え（"A Sample" -->"a_sample"）

- 全角空白や全角記号は無視、ただし '＿' だけはそのまま残す。



具体例：

```

## A Sample

## 『条文＿追加項目』案　その1

```



```

1. <a href="#a-sample">A Sample<a/>

1. <a href="#条文＿追加項目案その1">『条文＿追加項目』案　その1<a/>



```





- 見出しから生成した文字列が既に存在すれば末尾に '-数字'を付与する。たとえば

```

## あれ

## これ

## あれ

## あれ



```

という markdown 入力の場合、以下のように生成して区別します。





```

1. <a href="#あれ">あれ</a>

1. <a href="#これ">これ</a>

1. <a href="#あれ-1">あれ</a>

1. <a href="#あれ-2">あれ</a>

```





3. 見出しレベルと目次のレベルの対応

- 目次の書式は以下のようにします。



入力 markdown の具体例





```

## PREFACE

## First Chapter

## a2

## b2

## c2

### d3

#### e4

#### f4

#### g4

## h2

## i2

```



生成した目次の具体例（"--level 4" の場合）

```

目次



1. <a href="#preface">PREFACE</a>

1. <a href="#first-chapter">First Chapter</a>

1. <a href="#a2">a2</a>

1. <a href="#b2">b2</a>

1. <a href="#c2">c2</a>

     1. <a href="#d3">d3</a>

         1. <a href="#e4">e4</a>

         1. <a href="#f4">f4</a>

         1. <a href="#g4">g4</a>

1. <a href="#h2">h2</a>

1. <a href="#i2">i2</a>



```
"""
