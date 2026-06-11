# テーブル定義

| tableName | columnName | dataType | nullable | primaryKey | description |
| --- | --- | --- | --- | --- | --- |
| static_hosts | host_id | INTEGER | NO | YES | 静的ホストのID |
| static_hosts | hostname | TEXT | NO | NO | ホスト名 |
| static_hosts | ip_address | TEXT | YES | NO | IPアドレス |
| static_hosts | created_at | DATETIME | YES | NO | 作成日時 |
| static_hosts | updated_at | DATETIME | YES | NO | 更新日時 |
| self_records | record_id | INTEGER | NO | YES | レコードID |
| self_records | hostname | TEXT | YES | NO | ホスト名 |
| self_records | ip_address | TEXT | YES | NO | IPアドレス |
| self_records | record_type | TEXT | YES | NO | レコードタイプ |
| self_records | ttl | INTEGER | YES | NO | TTL |
| self_records | resolution_method | TEXT | YES | NO | 名前解決メソッド |
| self_records | updated_at | DATETIME | YES | NO | 更新日時 |
| other_records | hostname | TEXT | YES | NO | ホスト名 |
| other_records | ip_address | TEXT | YES | NO | IPアドレス |
| other_records | record_type | TEXT | YES | NO | レコードタイプ |
| other_records | ttl | INTEGER | YES | NO | TTL |
| merged_records | hostname | TEXT | YES | NO | マージ済みレコードのホスト名 |
| merged_records | ip_address | TEXT | YES | NO | マージ済みレコードのIPアドレス |
| merged_records | record_type | TEXT | YES | NO | マージ済みレコードのレコードタイプ |
| merged_records | ttl | INTEGER | YES | NO | マージ済みレコードのTTL |