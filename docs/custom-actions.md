# 独自アクションの実装

`sesame_remo.core`はSesame5とのBLE接続、OS3認証、切断後の再接続、`mechStatus`の状態遷移判定までを担当します。Nature RemoやmacOSのサウンド機能には依存しません。

`run_lock_monitor`へasync callbackを渡すことで、施錠・解錠時の動作を利用側で定義できます。

```python
import asyncio

from sesame_remo.core import LockStateEvent, SesameConfig, run_lock_monitor


async def on_unlocked(event: LockStateEvent) -> None:
    print(event.current_state, event.status.position)


async def on_locked(event: LockStateEvent) -> None:
    print(event.current_state, event.status.position)


async def main() -> None:
    config = SesameConfig(
        sesame_id="...",
        sesame_secret_key="...",
    )
    await run_lock_monitor(
        config,
        scan_timeout=10,
        poll_interval=2,
        on_unlocked=on_unlocked,
        on_locked=on_locked,
    )


asyncio.run(main())
```

`on_unlocked`と`on_locked`は、初回状態や同じ状態の重複通知では呼ばれません。すべての状態通知が必要な場合は`on_status`、切断時の後始末が必要な場合は`on_connection_lost`も指定できます。

`run_lock_monitor`は通常の切断やスキャンタイムアウトでは再試行を続けますが、安全に継続できないプロトコル異常ではcallbackへ停止イベントを通知してreturnします。常駐プロセスとして使う場合は、正常returnを無条件に再起動しないようプロセス管理側も設定してください。同梱のLaunchAgent plistは異常終了時だけ再起動します。

callbackは通知順にawaitされます。時間のかかる外部APIを状態監視と並行して実行したい場合は、利用側で`asyncio.create_task`などを使い、終了時に未完了タスクを回収してください。同梱の`sesame_remo.automation.SesameRemoActions`がその実装例です。
