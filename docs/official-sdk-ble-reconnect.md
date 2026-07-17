# 公式SDKのBLE接続調査

このメモは、CANDY HOUSEが公開しているSesameSDKのAndroid/iOSコードを調査した結果と、`sesame-remo`の状態監視方式を記録します。公式アプリの内部実装は将来変わる可能性があるため、確認した公開ソースへのリンクも残します。

## 共通する役割

SesameはBLE広告を定期的に送信します。状態監視では次の3段階を分けて考えます。

1. BLE広告を受信してSesameを発見する
2. BLE接続してログインする
3. 接続後の`mechStatus` publish通知で施錠状態を受け取る

## Android SDK

`CHBleManager`がBLEスキャンを開始し、登録済みデバイスが接続可能になるとアプリ側の`backgroundAutoConnect()`が`device.connect()`を呼びます。

- [CHBleManager.kt](https://github.com/CANDY-HOUSE/SesameSDK_Android_with_DemoApp/blob/master/sesame-sdk/src/main/java/co/candyhouse/sesame/open/CHBleManager.kt)
- [CHDeviceViewModel.kt](https://github.com/CANDY-HOUSE/SesameSDK_Android_with_DemoApp/blob/master/app/src/main/java/co/candyhouse/app/tabs/devices/model/CHDeviceViewModel.kt#L224-L243)
- [CHSesameOS3.kt](https://github.com/CANDY-HOUSE/SesameSDK_Android_with_DemoApp/blob/master/sesame-sdk/src/main/java/co/candyhouse/sesame/ble/os3/base/CHSesameOS3.kt)

公開ソースには、BLEの一般的な再接続を固定間隔で行う処理は見当たりません。広告を受信して再び接続可能になった時に接続を試すイベント駆動型です。

## iOS SDK

`CHBluetoothCenter`が`CBCentralManager`でスキャンを継続します。通常の登録済みデバイス一覧に対して、広告受信だけで自動接続する共通処理はAndroid版ほど明確ではなく、接続は各画面・各機能から要求されます。

- [CHBluetoothCenter.swift](https://github.com/CANDY-HOUSE/SesameSDK_iOS_with_DemoApp/blob/master/Sources/SesameSDK/Ble/CHBluetoothCenter.swift)
- [CHBaseDevice.swift](https://github.com/CANDY-HOUSE/SesameSDK_iOS_with_DemoApp/blob/master/Sources/SesameSDK/Ble/CHBaseDevice.swift#L96-L139)

自動解錠では2秒間隔のタイマーから未ログイン時に`connect()`を呼びますが、これは一般的な状態監視の再接続機構ではありません。

- [AppDelegate.swift](https://github.com/CANDY-HOUSE/SesameSDK_iOS_with_DemoApp/blob/master/SesameUI/SesameUI/Source/AppDelegate.swift#L103-L120)

## sesame-remoの採用方式

`sesame-remo monitor`は、BLEスキャナと認証済み接続を維持して`mechStatus`通知を待ちます。通知がしばらく来ないだけでは接続を切らず、BLEクライアントが実際に切断状態になった時に、対象Sesameの次の広告を待って再接続します。

接続中または切断処理中に届いた広告は次回接続に流用せず、切断完了後の新しい広告だけを再接続の起点にします。接続が失われた時点で音声を停止します。

監視処理はSesameの履歴を読み書きせず、操作元も判定しません。解錠状態への遷移は`mechStatus`から判断します。

## 状態監視ログ

標準出力はJSON Lines形式で、各行にUTCの`timestamp`と`event`を含みます。`status`には施錠状態、回転位置、payload、`state_changed`には状態遷移が入ります。広告受信、接続試行、接続成功、接続失敗、接続喪失、スキャンタイムアウト、スキャン停止も記録します。

実機でしか確認できなかった通知間隔、再接続、音声停止の挙動は[実機検証記録](field-verification.md)、現在の状態遷移は[状態遷移図](status-monitor-state-machine.md)を参照してください。
