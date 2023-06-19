# 群益即時資料處理程式 (py-skcom-quote)

 > 免責聲明：此專案仍處於測試階段，可能產生錯誤的結果，使用者應自行承擔使用風險。

這個專案的目的是讓串接群益API接收即時資料更加方便，並提供一些官方API不提供的功能。它目前提供了以下功能：

- 提供歷史K線，支援 M1, M5, M15, M30, H1
- 提供將即時Ticks轉換為即時K線的功能，支援 M1, M5, M15, M30, H1
- 支援證券與期貨

此程式使用 Python 3.7.9 開發。

## 環境安裝

1. 按照群益官方指示安裝 SKCOM.dll 及相關憑證。
2. 安裝所需套件：
```bash
pip install -r requirements.txt
```
3. 複製設定檔 `conn.example.yaml` 並命名為 `conn.yaml`，將 `luser` 和 `lpass` 改為登入使用的帳號和密碼。

## 使用方法

首先，啟動範例程式以接收K線資料：
```bash
python example_listener.py
```
然後，在命令列輸入以下指令以啟動資料源程式：
```bash
python main.py c1 38888
```
這樣即可開始接收歷史K線和即時K線資料。
