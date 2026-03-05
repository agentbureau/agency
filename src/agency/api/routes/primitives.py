import csv
import io
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from pydantic import BaseModel

router = APIRouter(prefix="/primitives", tags=["primitives"])

VALID_TABLES = {"role_components", "desired_outcomes", "trade_off_configs"}


class PrimitiveCreate(BaseModel):
    table: str
    description: str
    instance_id: str
    client_id: str | None = None
    project_id: str | None = None


@router.post("", status_code=201)
def create_primitive(req: PrimitiveCreate, request: Request):
    if req.table not in VALID_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid table: {req.table}")
    from agency.db.primitives import insert_primitive
    pid = insert_primitive(
        request.app.state.db,
        table=req.table,
        description=req.description,
        instance_id=req.instance_id,
        client_id=req.client_id,
        project_id=req.project_id,
    )
    return {"id": pid, "table": req.table, "description": req.description}


@router.post("/import", status_code=201)
async def import_primitives_csv(
    table: str,
    instance_id: str,
    request: Request,
    file: UploadFile = File(...),
):
    """
    Import primitives from a CSV file.
    Expected columns: description (required), client_id (optional), project_id (optional)
    """
    if table not in VALID_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid table: {table}")

    from agency.db.primitives import insert_primitive
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))

    if "description" not in (reader.fieldnames or []):
        raise HTTPException(status_code=422, detail="CSV must have a 'description' column")

    inserted, skipped = 0, 0
    for row in reader:
        desc = row.get("description", "").strip()
        if not desc:
            skipped += 1
            continue
        try:
            insert_primitive(
                request.app.state.db,
                table=table,
                description=desc,
                instance_id=instance_id,
                client_id=row.get("client_id") or None,
                project_id=row.get("project_id") or None,
            )
            inserted += 1
        except Exception:
            skipped += 1  # duplicate content hash

    return {"inserted": inserted, "skipped": skipped}


@router.get("/{table}")
def list_primitives(table: str, request: Request, limit: int = 50):
    if table not in VALID_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid table: {table}")
    rows = request.app.state.db.execute(
        f"SELECT id, description, created_at FROM {table} LIMIT ?", (limit,)
    ).fetchall()
    return [{"id": r[0], "description": r[1], "created_at": r[2]} for r in rows]


@router.delete("/{table}/{primitive_id}", status_code=204)
def delete_primitive(table: str, primitive_id: str, request: Request):
    if table not in VALID_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid table: {table}")
    result = request.app.state.db.execute(
        f"DELETE FROM {table} WHERE id = ?", (primitive_id,)
    )
    request.app.state.db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Primitive not found")
