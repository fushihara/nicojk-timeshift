# 概要

- 2020/12 にリニューアルしたニコニコ実況関連のツールです
- 1 つめの機能 コメントをsqlite 形式で保存。タイムシフトと、放送中のチャンネル両対応
- 2 つめの機能 ts ファイルの時間に対応しているコメント txt ファイルを作成

![img](https://github.com/fushihara/nicojk-timeshift/blob/main/markdown-images/2020-12-20_00-11-04.png?raw=true)

# 動作、開発環境

- python 3.8
- Windows 10
- pip で websockets peewee をインストールして下さい

# コメント保存機能

ニコニコ動画のプレミアムアカウントが必須です。<br>
`get-nico-comments-all.bat.sample`を bat にリネームし、ファイルの中のクッキーの値を書き換えて下さい。<br>
`./logs-nicolive/`フォルダが作成され、その中にニコニコ公式の実況 ch のログが作成されます。<br>
ログの取得対象はタイムシフトが有効になっている動画＆現在放送中の動画。

初回起動は、現在有効なタイムシフトと放送中の動画、全て受信するので時間がかかります。<br>
二度目以降は、新しいタイムシフトと放送中の動画のみ受信します。<br>
一日、もしくは一週間に一度実行させると、ログを貯める事が出来ると想定しています。<br>
(タイムシフトが一週間以上の場合)

コマンドラインオプションで、強制的に全タイムシフト受信、特定の局だけ受信の指定が出来ます。

# ts ファイルからコメント txt 作成機能

ts ファイルを`get-ts-comments.bat`にドラッグ＆ドロップすると、ts ファイルを解析し 放送時間のコメント.txt ファイルを作成します。<br>
ts ファイルの解析ロジックは http://jk.rutice.net/ を参考にさせて頂きました。<br>
リアルタイムでコメントファイルを保存出来なかった ts ファイルのコメントを受信する事を想定
