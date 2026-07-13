# sesame-remo

Sesame5 の BLE 履歴を Mac mini から読み、Sesame Touch Pro 経由の解錠だと判定できた場合に Nature Remo の照明 ON シグナルを送る最小 CLI です。

現時点の v1 は、まず実機の raw history payload を採取して Touch Pro 由来の判定ルールを確定する前提です。

## Setup

```bash
uv sync
cp config.example.toml config.toml
```

このプロジェクトは `.python-version` と `pyproject.toml` で Python 3.13 系に固定しています。

`config.toml` の値はサンプルのままでは動きません。Sesame5 の UUID / 16-byte secret key と Nature Remo の token / signal id を入れます。`config.toml` は Git の管理対象外です。

Sesame5 の UUID と secret key は、Sesame アプリで発行した owner または manager の共有リンクからローカルで取り出せます。共有リンク自体にも鍵が含まれるので、チャットなどへ貼らずクリップボードから直接渡してください。

```bash
pbpaste | uv run sesame-remo decode-qr
```

表示された2行を `config.toml` の同名項目へコピーします。guest鍵はCandy Houseサーバによる都度署名が必要なため、このBLE単独版では利用できません。

## Commands

履歴を採取します。最初はこれを使って Touch Pro / Sesame app / 手動解錠の payload 差分を見ます。

```bash
uv run sesame-remo history-dump --config config.toml --delete-after-read
```

1回の実行で履歴を1件取得します。JSON の `event_type` と `is_unlock` は公式SDK資料にある履歴種別（先頭4-byteの record ID に続く1 byte）から表示します。次の履歴へ進むにはそのレコードを Sesame5 から削除する必要があるため、Touch Pro / Sesame app / 手動のサンプル採取時は `--delete-after-read` を付けてください。削除した raw payload は標準出力に残りますが、Sesame アプリが後から取得する履歴からは消えます。

判定ルールを入れた後、常駐モードで実行します。

```bash
uv run sesame-remo daemon --config config.toml
```

## Touch Pro 判定

`touch_pro_match` が未設定の場合、daemon は誤って履歴を消費しないよう起動を拒否します。`history-dump` で採取した payload から、Touch Pro 由来にだけ出る byte pattern を設定してください。先頭4 byteの可変 record ID は判定対象から自動的に除外されます。

```toml
[touch_pro_match]
contains_hex = ["01020304"]
```

daemon は Touch Pro パターンに一致し、かつ履歴種別が解錠のときだけ照明を送信します。`delete_history_after_read = true` が必須です。Sesame5 の履歴取得はキューの先頭を読む方式なので、削除しない限り同じレコードから進めません。Nature Remo 送信が失敗した場合は削除せず、次のループで再試行します。

macOS で初回実行時に Bluetooth 利用許可が表示されたら、実行に使うターミナルを許可してください。タイムアウト時は UUID、Bluetooth 権限、距離、未取得履歴の有無を含むエラーを表示します。
