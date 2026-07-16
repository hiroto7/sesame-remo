# 公式SDKのBLE接続調査

このメモは、CANDY HOUSEが公開しているSesameSDKのAndroid/iOSコードを調査した結果と、`sesame-remo`の状態監視方式を記録するものです。公式アプリの内部実装は将来変わる可能性があるため、確認した公開ソースへのリンクも残します。

## 共通する役割

SesameはBLE広告（advertisement）を定期的に送信します。広告はデバイスの存在、デバイスID、製品種別、登録状態などを周囲へ知らせる短いパケットです。広告そのものは施錠・解錠イベントの詳細通知ではありません。

状態監視では、次の3段階を分けて考えます。

1. BLE広告を受信してSesameを発見する
2. BLE接続してログインする
3. 接続後の`mechStatus` publish通知で施錠状態を受け取る

## Android SDK

`CHBleManager`がBLEスキャンを開始し、受信した広告をデバイスマップへ保存します。登録済みデバイスの状態が`ReceivedAdV`になると、アプリ側の`backgroundAutoConnect()`が`device.connect()`を呼びます。

- [CHBleManager.kt](https://github.com/CANDY-HOUSE/SesameSDK_Android_with_DemoApp/blob/master/sesame-sdk/src/main/java/co/candyhouse/sesame/open/CHBleManager.kt)
- [CHDeviceViewModel.kt](https://github.com/CANDY-HOUSE/SesameSDK_Android_with_DemoApp/blob/master/app/src/main/java/co/candyhouse/app/tabs/devices/model/CHDeviceViewModel.kt#L224-L243)
- [CHSesameOS3.kt](https://github.com/CANDY-HOUSE/SesameSDK_Android_with_DemoApp/blob/master/sesame-sdk/src/main/java/co/candyhouse/sesame/ble/os3/base/CHSesameOS3.kt)

公開ソースには、BLEの一般的な再接続を「何秒ごと」とする固定間隔は見当たりません。広告を受信して再び接続可能になった時に接続を試すイベント駆動型です。Sesame 5の操作コマンドを2秒間隔で最大5回再送する処理はありますが、これは接続再試行とは別です。

## iOS SDK

`CHBluetoothCenter`が`CBCentralManager`でスキャンを継続します。広告はデバイスマップへ保存されますが、通常の登録済みデバイス一覧に対して、広告受信だけで自動接続する共通処理はAndroid版ほど明確ではありません。接続は各画面・各機能から要求されます。

- [CHBluetoothCenter.swift](https://github.com/CANDY-HOUSE/SesameSDK_iOS_with_DemoApp/blob/master/Sources/SesameSDK/Ble/CHBluetoothCenter.swift)
- [CHBaseDevice.swift](https://github.com/CANDY-HOUSE/SesameSDK_iOS_with_DemoApp/blob/master/Sources/SesameSDK/Ble/CHBaseDevice.swift#L96-L139)

例外は自動解錠です。バックグラウンドの自動解錠処理では2秒間隔のタイマーが動き、未ログインなら`connect()`を呼びます。これは一般的な状態監視の再接続機構ではありません。

- [AppDelegate.swift](https://github.com/CANDY-HOUSE/SesameSDK_iOS_with_DemoApp/blob/master/SesameUI/SesameUI/Source/AppDelegate.swift#L103-L120)

iOSのバックグラウンドBLE処理にはOSの制約があるため、ソース上の2秒間隔が実機で常に正確に実行されるとは限りません。

## sesame-remoの採用方式

`status-daemon`は、接続中もBLEスキャナを維持しながらBLE接続を維持して`mechStatus`通知を待ちます。切断・通知タイムアウト後は、対象Sesameの次の広告を待ち、その広告のデバイス情報で即座に接続を試します。接続が失われた時点で音声は停止します。

この方式により、従来の「最大10秒スキャンしてから2秒待つ」という再接続の空白をなくします。一方、接続中もスキャンを維持するため、Mac側のBluetooth処理負荷は増える可能性があります。Sesame側の広告送信回数はMacがスキャンしているかどうかで増えません。

履歴を読まないため、状態監視による履歴削除は発生しません。Touch Proだけを識別する履歴監視とは別用途です。
