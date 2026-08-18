# Homepage
私のホームページ/ポートフォリオです。
自作のHugoテーマを使ってビルドしています。

## セットアップ

Hugo `v0.164.0` とuvを使用します。

```
$ git clone https://github.com/zzzmisa/hugo-theme-doors.git themes/hugo-theme-doors
$ git -C themes/hugo-theme-doors checkout 98ced35c86b3db9c0ff53ee081b04b31dfc523a9
```

使用するテーマは上記のコミットに固定します。

サムネイル生成ツールはuvで実行します。Pillowはスクリプトに宣言されたバージョンが
隔離環境へ自動的にインストールされます。

```
$ uv run tools/make_thumbnail.py app_icon.png static/images/thumbnail.png
```

## ローカル確認

```
$ hugo server
```

ブラウザで `http://localhost:1313` にアクセスします。開発サーバーの生成先は
Hugo標準の `public/` であり、公開用の `docs/` は更新しません。

## 公開用ビルド

```
$ hugo
```

サイトは `docs/` 以下へクリーンビルドされます。

GitHub Actionsでは公開用ビルドを再実行し、ビルド結果とコミット済みの `docs/` が
一致することを確認します。

```
$ git diff --exit-code -- docs
```
