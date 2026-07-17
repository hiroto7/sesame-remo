# 実機検証記録

現在の実装は、Sesame5の`mechStatus`による状態監視を唯一の解錠判定として使用します。解錠状態への遷移でNature Remo照明をONにし、音声を再生します。

実機で確認する項目:

- Sesame5の広告検出と認証済みBLE接続
- 施錠中から解錠中への`mechStatus`遷移
- 解錠遷移後のNature Cloud API呼び出し
- 施錠・BLE切断・監視終了時の音声停止
- Nature API失敗後もBLE監視が継続すること
