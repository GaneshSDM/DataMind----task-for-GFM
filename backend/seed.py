"""Seed: create admin user only if not exists. Use existing roles from DB."""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import SessionLocal, engine, Base
import app.models.user  # noqa
from app.models.user import User, Role, UserRole, DBConnection
from app.core.security import get_password_hash
from app.core.config import settings

Base.metadata.create_all(bind=engine)
db = SessionLocal()

try:
    # Print existing roles
    roles = db.query(Role).all()
    print(f"\n📋 Existing roles ({len(roles)}):")
    for r in roles:
        print(f"   [{r.role_id}] {r.role_name}")

    # Use first admin-like role, fallback to first role
    admin_role = db.query(Role).filter(Role.role_name.ilike("%admin%")).first()
    if not admin_role:
        admin_role = db.query(Role).first()
    if not admin_role:
        print("❌ No roles found in DB. Add roles first.")
        exit(1)
    print(f"\n✅ Using role: [{admin_role.role_id}] {admin_role.role_name}")

    # Check existing users
    users = db.query(User).all()
    print(f"\n👥 Existing users ({len(users)}):")
    for u in users:
        print(f"   [{u.user_id}] {u.email}")

    # Create admin user only if not exists
    admin = db.query(User).filter(User.email == "admin@slm.local").first()
    if not admin:
        admin = User(
            first_name="Admin", last_name="User",
            email="admin@slm.local",
            password_hash=get_password_hash("Admin@1234"),
            is_active=True,
        )
        db.add(admin)
        db.flush()
        # Check if UserRole already exists
        existing_ur = db.query(UserRole).filter(
            UserRole.user_id == admin.user_id,
            UserRole.role_id == admin_role.role_id
        ).first()
        if not existing_ur:
            db.add(UserRole(user_id=admin.user_id, role_id=admin_role.role_id, is_active=True))
        print(f"\n✅ Created admin user")
    else:
        print(f"\n✅ Admin user already exists")

    # Register Supabase connection if not exists
    match = re.match(r'postgresql://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(\S+)', settings.DATABASE_URL)
    if match:
        db_user, db_pass, db_host = match.group(1), match.group(2), match.group(3)
        db_port = int(match.group(4)) if match.group(4) else 5432
        db_name = match.group(5)
        existing = db.query(DBConnection).filter(DBConnection.connection_name == "Supabase (Default)").first()
        if not existing:
            db.add(DBConnection(
                connection_name="Supabase (Default)",
                host=db_host, port=db_port, database_name=db_name,
                username=db_user, password_encrypted=db_pass, is_active=True,
            ))
            print(f"✅ Registered DB connection: {db_host}:{db_port}/{db_name}")

    db.commit()
    print("\n✅ Seed complete.")
    print("   Email:    admin@slm.local")
    print("   Password: Admin@1234")

except Exception as e:
    db.rollback()
    print(f"❌ Seed failed: {e}")
    raise
finally:
    db.close()
