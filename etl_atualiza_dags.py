from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago


def grant_etl_permissions_to_viewer():
    from airflow.www.app import cached_app
    from airflow.models import DagModel

    app = cached_app()

    with app.app_context():
        sm = app.appbuilder.sm
        session = sm.get_session

        viewer_role = sm.find_role("Viewer")
        if not viewer_role:
            raise ValueError("Role 'Viewer' não encontrado.")

        etl_dags = (
            session.query(DagModel)
            .filter(
                DagModel.dag_id.like("etl_%"),
                DagModel.is_active == True,
            )
            .all()
        )

        print(f"[INFO] {len(etl_dags)} DAGs etl_ encontradas.")

        for dag in etl_dags:
            resource_name = f"DAG:{dag.dag_id}"
            for action in ["can_read", "can_edit"]:
                sm.add_view_menu(resource_name)
                perm = sm.add_permission_view_menu(action, resource_name)
                if perm not in viewer_role.permissions:
                    sm.add_permission_role(viewer_role, perm)
                    print(f"  ✔ {action} on {resource_name}")
                else:
                    print(f"  — Já existe: {action} on {resource_name}")

        print("[INFO] Concluído.")


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
