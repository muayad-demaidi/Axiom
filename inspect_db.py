import sqlite3

def inspect_db():
    conn = sqlite3.connect('axiom_dev.db')
    cursor = conn.cursor()
    
    print("Tables in database:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    for table in tables:
        table_name = table[0]
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"Table: {table_name}, Count: {count}")
    
    conn.close()

if __name__ == "__main__":
    inspect_db()
