# sesame-remo

Sesame5 の BLE 履歴を Mac mini から読み、Sesame Touch Pro 経由の解錠だと判定できた場合に Nature Remo の照明 ON シグナルを送る最小 CLI です。

現時点の v1 は、まず実機の raw history payload を採取して Touch Pro 由来の判定ルールを確定する前提です。

## Setup

```bash
uv sync
cp config.example.toml config.toml
```

`config.toml` に Sesame5 の UUID / secret key と Nature Remo の token / signal id を入れます。

## Commands

履歴を採取します。最初はこれを使って Touch Pro / Sesame app / 手動解錠の payload 差分を見ます。

```bash
uv run python -m sesame_remo history-dump --config config.toml
```

判定ルールを入れた後、常駐モードで実行します。

```bash
uv run python -m sesame_remo daemon --config config.toml
```

## Touch Pro 判定

`touch_pro_match` が未設定の場合、daemon は照明を送信しません。`history-dump` で採取した payload から、Touch Pro 由来にだけ出る byte pattern を設定してください。

```toml
[touch_pro_match]
contains_hex = ["01020304"]
```

`delete_history_after_read = true` にすると、読み取った履歴 record id を Sesame5 から削除します。公式 SDK もサーバ送信後に削除していますが、この CLI はサーバへ履歴を送らないため、履歴を Sesame アプリ側に残したい場合は false のままにしてください。false のままだと同じ古い record が繰り返し返り、以後の履歴取得が詰まる可能性があります。
