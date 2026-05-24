"""Test Supabase connection with all possible methods."""
import psycopg2
import socket

password = "Decision@2026Pondi"
dbname = "postgres"

hosts = [
    # Direct - only IPv6, won't work in WSL
    ("db.vhnksqufndudqpoxwmkd.supabase.co", 5432, "postgres", "require"),
    # Pooler session mode
    ("aws-0-ap-southeast-1.pooler.supabase.com", 5432, "postgres", "require"),
    # Pooler transaction mode
    ("aws-0-ap-southeast-1.pooler.supabase.com", 6543, "postgres", "require"),
]

for host, port, user, sslmode in hosts:
    print(f"\n{'='*60}")
    print(f"Trying: {user}@{host}:{port} sslmode={sslmode}")
    
    # Check DNS
    try:
        for fam in [socket.AF_INET]:
            addrs = socket.getaddrinfo(host, port, fam)
            ips = set(a[4][0] for a in addrs)
            print(f"  DNS (IPv4): {ips}")
    except Exception as e:
        print(f"  DNS: {e}")
    
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
            sslmode=sslmode,
            connect_timeout=8,
        )
        print("  >>> CONNECTED! <<<")
        cur = conn.cursor()
        cur.execute("SELECT version()")
        ver = cur.fetchone()
        print(f"  Version: {ver[0][:80]}")
        
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='tracopp'")
        tables = [r[0] for r in cur.fetchall()]
        print(f"  Tables: {tables}")
        
        cur.close()
        conn.close()
        print("\n  ✓ Connection successful!")
        break
    except Exception as e:
        msg = str(e).strip()
        # Keep only the FATAL part
        for line in msg.split('\n'):
            if 'FATAL' in line or 'timeout' in line.lower() or 'unreachable' in line.lower():
                print(f"  ✗ {line.strip()[:150]}")
                break
        else:
            print(f"  ✗ {msg[:150]}")

print("\nDone.")
