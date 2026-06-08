from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago


def grant_etl_permissions_to_viewer():
    from airflow.settings import Session
    from sqlalchemy import text

    session = Session()

    try:
        viewer_role = session.execute(
            text("SELECT id FROM ab_role WHERE name = 'Viewer'")
        ).fetchone()

        if not viewer_role:
            raise ValueError("Role 'Viewer' não encontrado.")

        viewer_role_id = viewer_role[0]
        print(f"[INFO] Viewer role id: {viewer_role_id}")

        etl_dags = session.execute(
            text("SELECT dag_id FROM dag WHERE dag_id LIKE 'etl_%' AND is_active = true")
        ).fetchall()

        print(f"[INFO] {len(etl_dags)} DAGs encontradas.")

        for (dag_id,) in etl_dags:
            resource_name = f"DAG:{dag_id}"

            for action_name in ["can_read", "can_edit"]:

                # Garante view_menu
                session.execute(text("""
                    INSERT INTO ab_view_menu (name)
                    VALUES (:name)
                    ON CONFLICT (name) DO NOTHING
                """), {"name": resource_name})

                # Garante permission
                session.execute(text("""
                    INSERT INTO ab_permission (name)
                    VALUES (:action)
                    ON CONFLICT (name) DO NOTHING
                """), {"action": action_name})

                # Garante permission_view_menu
                session.execute(text("""
                    INSERT INTO ab_permission_view_menu (permission_id, view_menu_id)
                    SELECT p.id, vm.id
                    FROM ab_permission p, ab_view_menu vm
                    WHERE p.name = :action AND vm.name = :resource
                    ON CONFLICT DO NOTHING
                """), {"action": action_name, "resource": resource_name})

                # Garante vínculo com o role Viewer
                session.execute(text("""
                    INSERT INTO ab_permission_view_role (permission_view_id, role_id)
                    SELECT pvm.id, :role_id
                    FROM ab_permission_view_menu pvm
                    JOIN ab_permission p ON p.id = pvm.permission_id
                    JOIN ab_view_menu vm ON vm.id = pvm.view_menu_id
                    WHERE p.name = :action AND vm.name = :resource
                    ON CONFLICT DO NOTHING
                """), {"role_id": viewer_role_id, "action": action_name, "resource": resource_name})

                print(f"  ✔ {action_name} on {resource_name}")

        session.commit()
        print("[INFO] Concluído com sucesso.")

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


with DAG(
    dag_id="admin_grant_etl_permissions_to_viewer",
    schedule_interval=None,
    start_date=days_ago(1),
    catchup=False,
    tags=["admin", "permissões"],
) as dag:

    PythonOperator(
        task_id="grant_etl_permissions_to_viewer",
        python_callable=grant_etl_permissions_to_viewer,
    )
