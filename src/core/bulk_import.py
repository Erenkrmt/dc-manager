"""Bulk import companies from CSV for admin use."""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone, timedelta
#
# from typing import Optional

from src.core import database as db

logger = logging.getLogger(__name__)


def import_companies_from_csv(csv_text: str) -> dict:
    """
    Import or update companies from CSV text.

    CSV columns (comma-separated, header row optional):
      Discord,Company Name,Tier,Access Expires,Active,Trial Used,ID

    - If ID is provided and the company exists, it will be updated.
    - If ID is provided but the company doesn't exist, a new company
      is created with that ID (SQLite: AUTOINCREMENT may override).
    - If ID is empty/0, a new company is created with a generated API key.

    Returns a summary dict with counts and any errors.
    """
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
        try:

            def _safe(val: str | None) -> str:
                return (val or "").strip()

            company_id_str = _safe(row.get("ID"))
            company_name = _safe(row.get("Company Name"))
            tier = _safe(row.get("Tier")).lower() or "free"
            access_expires = _safe(row.get("Access Expires"))
            active_str = _safe(row.get("Active")) or "1"
            trial_used_str = _safe(row.get("Trial Used")) or "0"
            # discord = _safe(row.get("Discord"))

            is_active = 1 if active_str in ("1", "true", "yes") else 0
            trial_used = int(trial_used_str) if trial_used_str.isdigit() else 0
            tier = tier if tier in ("free", "premium") else "free"

            # Validate access_expires is a valid date string or empty
            if access_expires:
                try:
                    datetime.strptime(access_expires, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    errors.append(
                        f"Row {row_num}: Invalid date format '{access_expires}' — expected YYYY-MM-DD HH:MM:SS"
                    )
                    skipped += 1
                    continue

            ph = db._ph()
            conn = db.get_connection()
            try:
                cursor = conn.cursor()

                if company_id_str and company_id_str.isdigit():
                    company_id = int(company_id_str)
                    # Check if company exists
                    cursor.execute(
                        f"SELECT id FROM companies WHERE id = {ph}",
                        (company_id,),
                    )
                    existing = cursor.fetchone()

                    if existing:
                        # Update existing company
                        cursor.execute(
                            f"""UPDATE companies SET
                                company_name = {ph},
                                tier = {ph},
                                access_expires_at = {ph},
                                is_active = {ph},
                                trial_used = {ph},
                                updated_at = {ph}
                            WHERE id = {ph}""",
                            (
                                company_name,
                                tier,
                                access_expires or None,
                                is_active,
                                trial_used,
                                now,
                                company_id,
                            ),
                        )
                        conn.commit()
                        updated += 1
                        logger.info(
                            "Company ID %d updated: %s",
                            company_id,
                            company_name or "(no name)",
                        )
                    else:
                        # Create new company with specified ID
                        raw_api_key = db._generate_api_key()
                        hashed_key = db._hash_api_key(raw_api_key)
                        invite_code = db._generate_invite_code()

                        cursor.execute(
                            f"""INSERT INTO companies
                                (id, api_key, company_name, access_expires_at,
                                 is_active, trial_used, tier, invite_code,
                                 created_at, updated_at)
                                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
                            (
                                company_id,
                                hashed_key,
                                company_name,
                                access_expires or None,
                                is_active,
                                trial_used,
                                tier,
                                invite_code,
                                now,
                                now,
                            ),
                        )
                        conn.commit()
                        created += 1
                        logger.info(
                            "Company ID %d created with API key: %s",
                            company_id,
                            raw_api_key,
                        )
                else:
                    # No ID — create new company (auto-increment ID)
                    raw_api_key = db._generate_api_key()
                    hashed_key = db._hash_api_key(raw_api_key)
                    invite_code = db._generate_invite_code()

                    # Set trial end if trial wasn't used yet
                    trial_end = None
                    if trial_used == 0:
                        from src.core.settings import get_settings

                        trial_days = get_settings().TRIAL_DAYS
                        if trial_days > 0:
                            trial_end = (datetime.now(timezone.utc) + timedelta(days=trial_days)).strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                    access = access_expires or trial_end

                    cursor.execute(
                        f"""INSERT INTO companies
                            (api_key, company_name, access_expires_at,
                             is_active, trial_used, tier, invite_code,
                             created_at, updated_at)
                            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
                        (
                            hashed_key,
                            company_name,
                            access,
                            is_active,
                            trial_used,
                            tier,
                            invite_code,
                            now,
                            now,
                        ),
                    )
                    conn.commit()

                    # Get the new company ID
                    if db._USE_POSTGRES:
                        cursor.execute("SELECT LASTVAL()")
                        new_id = cursor.fetchone()["lastval"]
                    else:
                        new_id = cursor.lastrowid

                    created += 1
                    logger.info(
                        "Company ID %d created from CSV with API key: %s",
                        new_id,
                        raw_api_key,
                    )

            except Exception as exc:
                conn.rollback()
                errors.append(f"Row {row_num}: {exc}")
                logger.exception("Failed to import row %d: %s", row_num, exc)
                skipped += 1
            finally:
                conn.close()

        except Exception as exc:
            errors.append(f"Row {row_num}: {exc}")
            skipped += 1

    summary = {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info(
        "Import complete: %d created, %d updated, %d skipped, %d errors.",
        created,
        updated,
        skipped,
        len(errors),
    )
    return summary
