# API仕様書

| endpoint | method | description | requestBody | responseBody | auth |
| --- | --- | --- | --- | --- | --- |
| /api/merged-records | GET | 外部クライアントからの要求に応じ、データベース内のマージ済みレコード一覧をJSON形式で返却する。 |  |  | [object Object] |
| /api/other-records | POST | 他のmDNSプロキシノードから送信されるレコードを受信し、他プロキシレコードとして登録する。 | [object Object] |  | [object Object] |