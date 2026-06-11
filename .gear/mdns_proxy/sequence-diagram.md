# シーケンス図

## API機能

外部クライアントからの要求に応じ、マージ済みレコード一覧をJSONで返却する

**参加者:** クライアント (actor)、APIサーバー (system)、データベース (database)

**メッセージフロー:**
- クライアント → APIサーバー: GET /api/merged-records
- APIサーバー → データベース: SELECT merged_records
  - データベース ← APIサーバー: マージ済みレコード一覧
  - APIサーバー ← クライアント: JSONレスポンス

```mermaid
sequenceDiagram
    actor client as クライアント
    participant api as APIサーバー
    participant db as データベース
    client->>api: GET /api/merged-records
    api->>db: SELECT merged_records
    db-->>api: マージ済みレコード一覧
    api-->>client: JSONレスポンス
```

## API機能

他ノードから送信されるレコードを受信し、other_recordsに登録・更新する

**参加者:** 他のプロキシノード (system)、APIサーバー (system)、データベース (database)

**メッセージフロー:**
- 他のプロキシノード → APIサーバー: POST /api/other-records (Token付与)
- APIサーバー → APIサーバー: トークン検証とノードID抽出
- APIサーバー → データベース: INSERT/UPDATE other_records
  - データベース ← APIサーバー: 登録完了
  - APIサーバー ← 他のプロキシノード: 200 OK

```mermaid
sequenceDiagram
    participant other_proxy as 他のプロキシノード
    participant api as APIサーバー
    participant db as データベース
    other_proxy->>api: POST /api/other-records (Token付与)
    api->>api: トークン検証とノードID抽出
    api->>db: INSERT/UPDATE other_records
    db-->>api: 登録完了
    api-->>other_proxy: 200 OK
```

## CLI機能

CLIを通じて静的ホストを登録する

**参加者:** 管理者 (actor)、CLI (system)、データベース (database)

**メッセージフロー:**
- 管理者 → CLI: メニュー「3」選択とホスト情報入力
- CLI → データベース: INSERT static_hosts
  - データベース ← CLI: 登録完了
  - CLI ← 管理者: 追加完了メッセージ表示

```mermaid
sequenceDiagram
    actor admin as 管理者
    participant cli as CLI
    participant db as データベース
    admin->>cli: メニュー「3」選択とホスト情報入力
    cli->>db: INSERT static_hosts
    db-->>cli: 登録完了
    cli-->>admin: 追加完了メッセージ表示
```

## コア機能

ネットワーク上のmDNSクエリを受信し、該当するレコードがあれば応答する

**参加者:** ネットワーククライアント (actor)、mDNSサーバー (system)、データベース (database)

**メッセージフロー:**
- ネットワーククライアント → mDNSサーバー: UDP 5353 mDNSクエリ受信
- mDNSサーバー → データベース: マージ済みレコード等と照合
  - データベース ← mDNSサーバー: 照合結果
- mDNSサーバー → ネットワーククライアント: 名前解決結果の応答パケット送信

```mermaid
sequenceDiagram
    actor network_client as ネットワーククライアント
    participant mdns_server as mDNSサーバー
    participant db as データベース
    network_client-->>mdns_server: UDP 5353 mDNSクエリ受信
    mdns_server->>db: マージ済みレコード等と照合
    db-->>mdns_server: 照合結果
    mdns_server-->>network_client: 名前解決結果の応答パケット送信
```

## バッチ機能

一定間隔でクリーンアップ、名前解決、プロキシ発見、レコード同期、マージ処理を実行する

**参加者:** タイマー (actor)、常駐処理 (system)、名前解決機能 (system)、他のプロキシノード (system)、データベース (database)

**メッセージフロー:**
- タイマー → 常駐処理: インターバル経過
- 常駐処理 → データベース: レコードクリーンアップ（期限切れ削除）
  - データベース ← 常駐処理: 完了
- 常駐処理 → 名前解決機能: resolve_all実行
- 名前解決機能 → データベース: 静的ホスト一覧取得
  - データベース ← 名前解決機能: static_hosts一覧
- 名前解決機能 → 名前解決機能: 生mDNSクエリ・pingによる実在確認
- 名前解決機能 → データベース: self_recordsへ更新・登録
  - データベース ← 名前解決機能: 完了
  - 名前解決機能 ← 常駐処理: 名前解決完了
- 常駐処理 → 他のプロキシノード: プロキシ発見・レコード同期
  - 他のプロキシノード ← 常駐処理: 同期結果
- 常駐処理 → データベース: マージ処理（merged_records更新）
  - データベース ← 常駐処理: マージ完了

```mermaid
sequenceDiagram
    actor timer as タイマー
    participant scheduler as 常駐処理
    participant dns_resolver as 名前解決機能
    participant other_proxy as 他のプロキシノード
    participant db as データベース
    timer-->>scheduler: インターバル経過
    scheduler->>db: レコードクリーンアップ（期限切れ削除）
    db-->>scheduler: 完了
    scheduler->>dns_resolver: resolve_all実行
    dns_resolver->>db: 静的ホスト一覧取得
    db-->>dns_resolver: static_hosts一覧
    dns_resolver->>dns_resolver: 生mDNSクエリ・pingによる実在確認
    dns_resolver->>db: self_recordsへ更新・登録
    db-->>dns_resolver: 完了
    dns_resolver-->>scheduler: 名前解決完了
    scheduler->>other_proxy: プロキシ発見・レコード同期
    other_proxy-->>scheduler: 同期結果
    scheduler->>db: マージ処理（merged_records更新）
    db-->>scheduler: マージ完了
```
