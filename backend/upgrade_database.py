#!/usr/bin/env python3
"""
資料庫升級腳本 - 新增微台指表格
執行此腳本升級現有資料庫以支援 MXF 微台指數據
"""
import sqlite3
import sys
from pathlib import Path

def upgrade_database(db_path='data/market_data.db'):
    """升級資料庫 schema"""
    
    print(f"\n{'='*60}")
    print("資料庫升級工具 v2.0")
    print(f"目標資料庫: {db_path}")
    print(f"{'='*60}\n")
    
    if not Path(db_path).exists():
        print(f"✗ 資料庫不存在: {db_path}")
        print("  請先執行 data_collector.py 建立資料庫")
        sys.exit(1)
    
    # 備份
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"[1/3] 備份資料庫...")
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"  ✓ 已備份至: {backup_path}")
    except Exception as e:
        print(f"  ✗ 備份失敗: {e}")
        sys.exit(1)
    
    # 升級
    print(f"\n[2/3] 升級 schema...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 檢查 mxf_futures_data 表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='mxf_futures_data'
        """)
        
        if cursor.fetchone():
            print("  ℹ mxf_futures_data 表已存在，跳過創建")
        else:
            print("  • 創建 mxf_futures_data 表...")
            cursor.execute('''
                CREATE TABLE mxf_futures_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    commodity_id TEXT DEFAULT 'MXF',
                    close_price REAL,
                    total_oi INTEGER,
                    
                    -- 法人部位
                    dealers_long INTEGER,
                    dealers_short INTEGER,
                    dealers_net INTEGER,
                    trusts_long INTEGER,
                    trusts_short INTEGER,
                    trusts_net INTEGER,
                    foreign_long INTEGER,
                    foreign_short INTEGER,
                    foreign_net INTEGER,
                    institutional_net INTEGER,
                    
                    -- 散戶部位
                    retail_long INTEGER,
                    retail_short INTEGER,
                    retail_net INTEGER,
                    retail_ratio REAL,
                    
                    timestamp TEXT,
                    UNIQUE(date)
                )
            ''')
            print("  ✓ mxf_futures_data 表創建成功")
        
        # 檢查舊表是否存在必要欄位
        cursor.execute("PRAGMA table_info(futures_data)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'pcr_volume' not in columns:
            print("  • 在 futures_data 表中新增 pcr_volume 欄位...")
            cursor.execute('ALTER TABLE futures_data ADD COLUMN pcr_volume REAL')
            print("  ✓ pcr_volume 欄位新增成功")
        else:
            print("  ℹ futures_data 表已有 pcr_volume 欄位")
        
        conn.commit()
        print("\n  ✓ Schema 升級完成")
        
    except Exception as e:
        print(f"\n  ✗ 升級失敗: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()
    
    # 驗證
    print(f"\n[3/3] 驗證升級...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' 
        ORDER BY name
    """)
    
    tables = [row[0] for row in cursor.fetchall()]
    print(f"  資料庫表格: {', '.join(tables)}")
    
    # 檢查 mxf 表結構
    cursor.execute("PRAGMA table_info(mxf_futures_data)")
    mxf_columns = cursor.fetchall()
    print(f"\n  mxf_futures_data 表共 {len(mxf_columns)} 個欄位:")
    for col in mxf_columns[:5]:
        print(f"    • {col[1]} ({col[2]})")
    if len(mxf_columns) > 5:
        print(f"    ... 還有 {len(mxf_columns) - 5} 個欄位")
    
    conn.close()
    
    print(f"\n{'='*60}")
    print("✓ 資料庫升級成功!")
    print(f"{'='*60}\n")
    print("下一步:")
    print("1. 執行 python data_collector_v2.py 開始收集微台指數據")
    print("2. 查看 data/futures_data.json 確認數據格式")
    print("3. 更新前端代碼讀取新的 JSON 格式")
    print("")

if __name__ == '__main__':
    from datetime import datetime
    
    # 可以透過命令列參數指定資料庫路徑
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = 'data/market_data.db'
    
    upgrade_database(db_path)
