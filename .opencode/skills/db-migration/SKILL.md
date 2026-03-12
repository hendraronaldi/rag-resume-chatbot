---
name: db-migration
description: Database migration management for this project. Covers migration tools, commands, rollback procedures, and seeder patterns.
license: MIT
compatibility: Requires Alembic or similar migration tool.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.2.0"
---

**HIGH-RISK**: Database migrations can cause data loss. Always backup data before running migrations in production. Test thoroughly in development first.

---

## Migration Tool

This project uses **Alembic** for database migrations (recommended for SQLAlchemy).

### Installation
```bash
pip install alembic sqlalchemy
```

### Initialize Alembic (one-time setup)
```bash
alembic init alembic
```

This creates:
```
project/
├── alembic/
│   ├── env.py           # Migration environment
│   ├── script.py.mako   # Template for migrations
│   └── versions/        # Migration files
├── app/
│   └── models.py        # SQLAlchemy models
├── alembic.ini          # Alembic config
└── requirements.txt
```

---

## Exact Commands

### Create a new migration
```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "add_users_table"

# Create empty migration (manual changes)
alembic revision -m "create_feedback_table"
```

### Run all pending migrations
```bash
# Apply all migrations
alembic upgrade head

# Apply to specific revision
alembic upgrade +1
alembic upgrade abc123
```

### Rollback (UNDO migrations)
```bash
# Rollback last migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade abc123

# Rollback all migrations
alembic downgrade base
```

### Check status
```bash
# Show current revision
alembic current

# Show migration history
alembic history --verbose

# Show pending migrations
alembic check
```

---

## Rollback Steps (Critical)

**NEVER run downgrade in production without explicit approval.**

### Safe rollback procedure
```bash
# 1. Backup production database
pg_dump production_db > backup_$(date +%Y%m%d).sql

# 2. Verify current migration
alembic current

# 3. Rollback ONE migration at a time
alembic downgrade -1

# 4. Verify application still works
curl https://your-api/health

# 5. If issues, roll forward again
alembic upgrade +1
```

### Emergency rollback
```bash
# Rollback all to clean state (destroys all tables!)
alembic downgrade base

# Or manually restore from backup
psql production_db < backup_20240101.sql
```

---

## Naming Conventions

### Migration file naming
Format: `<timestamp>_<description>.py`

```
alembic/versions/
├── 20240101_001_initial_create_users.py
├── 20240115_002_add_email_unique_constraint.py
├── 20240201_003_create_feedback_table.py
└── 20240210_004_add_resume_embeddings.py
```

### Migration description rules
- Use imperative mood: "add", "create", "remove", "alter"
- Include table name: "add_users_table" NOT "add_users"
- Be specific: "add_email_unique_constraint" NOT "add_constraints"

---

## Migration File Structure

### Auto-generated migration (review before running!)
```python
# alembic/versions/20240101_001_initial_create_users.py
"""add_users_table

Revision ID: abc123
Revises: 
Create Date: 2024-01-01 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = 'abc123'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

def downgrade() -> None:
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
```

---

## Seeder Patterns

Seeders populate the database with initial/test data.

### Seeder file location
```
project/
├── app/
│   ├── models.py
│   └── seeders/
│       ├── __init__.py
│       ├── user_seeder.py
│       └── resume_seeder.py
└── seed.py              # Entry point
```

### Creating a seeder
```python
# app/seeders/user_seeder.py
from sqlalchemy.orm import Session
from app.models import User
from app.database import SessionLocal
from typing import List

def seed_users(count: int = 10) -> List[User]:
    """Seed test users into database."""
    db: Session = SessionLocal()
    try:
        users = []
        for i in range(count):
            user = User(
                email=f"user{i}@example.com",
                name=f"Test User {i}",
                created_at=func.now()
            )
            db.add(user)
            users.append(user)
        
        db.commit()
        for user in users:
            db.refresh(user)
        return users
    finally:
        db.close()

def clear_users():
    """Clear all users from database."""
    db: Session = SessionLocal()
    try:
        db.query(User).delete()
        db.commit()
    finally:
        db.close()
```

### Running seeders
```python
# seed.py
from app.seeders.user_seeder import seed_users, clear_users

def main():
    print("Clearing existing data...")
    clear_users()
    
    print("Seeding users...")
    users = seed_users(10)
    print(f"Created {len(users)} users")

if __name__ == "__main__":
    main()
```

Run with:
```bash
python seed.py
```

---

## Common Migration Scenarios

### Add a new column
```python
# Create migration
alembic revision --autogenerate -m "add_age_column_to_users"

# In upgrade():
op.add_column('users', sa.Column('age', sa.Integer(), nullable=True))

# In downgrade():
op.drop_column('users', 'age')
```

### Rename a table
```python
op.rename_table('user', 'users')
```

### Add foreign key
```python
op.add_column('feedback', 
    sa.Column('user_id', sa.Integer(), nullable=True))
op.create_foreign_key(
    'fk_feedback_user',
    'feedback', 'users',
    ['user_id'], ['id']
)
```

---

## Testing Migrations

### Test migrations locally
```bash
# Create test database
createdb test_db

# Run migrations on test DB
alembic upgrade head -c alembic_test.ini

# Run seeders
python seed.py

# Run tests
pytest tests/

# Cleanup
dropdb test_db
```

---

## Production Deployment Checklist

- [ ] Backup production database
- [ ] Test migration in staging first
- [ ] Run migration during low-traffic window
- [ ] Monitor application logs after migration
- [ ] Verify data integrity
- [ ] Have rollback plan ready

---

## Troubleshooting

### Migration fails
```bash
# Check current state
alembic current
alembic history

# Manually mark migration as applied (if safe)
alembic stamp <revision>
```

### Dependency issues
```bash
# Show migration dependencies
alembic history --verbose

# Fix by creating merge migration
alembic revision --merge -m "merge_heads"
```

(End of file - total 271 lines)
