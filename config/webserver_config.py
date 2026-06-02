#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Default configuration for the Airflow webserver."""

from __future__ import annotations

import os

from flask_appbuilder.const import AUTH_DB
from flask_appbuilder.security.manager import AUTH_LDAP

# from airflow.www.fab_security.manager import AUTH_LDAP
# from airflow.www.fab_security.manager import AUTH_OAUTH
# from airflow.www.fab_security.manager import AUTH_OID
# from airflow.www.fab_security.manager import AUTH_REMOTE_USER


basedir = os.path.abspath(os.path.dirname(__file__))

# Flask-WTF flag for CSRF
WTF_CSRF_ENABLED = True
WTF_CSRF_TIME_LIMIT = None

# ----------------------------------------------------
# AUTHENTICATION CONFIG
# ----------------------------------------------------
# For details on how to set up each of the following authentication, see
# http://flask-appbuilder.readthedocs.io/en/latest/security.html# authentication-methods
# for details.

# The authentication type
# AUTH_OID : Is for OpenID
# AUTH_DB : Is for database
# AUTH_LDAP : Is for LDAP
# AUTH_REMOTE_USER : Is for using REMOTE_USER from web server
# AUTH_OAUTH : Is for OAuth
AUTH_TYPE = AUTH_DB
AUTH_TYPE = AUTH_LDAP

# Uncomment to setup Full admin role name
# AUTH_ROLE_ADMIN = 'Admin'

# Uncomment and set to desired role to enable access without authentication
# AUTH_ROLE_PUBLIC = 'Viewer'

# Will allow user self registration
# AUTH_USER_REGISTRATION = True

# The recaptcha it's automatically enabled for user self registration is active and the keys are necessary
# RECAPTCHA_PRIVATE_KEY = PRIVATE_KEY
# RECAPTCHA_PUBLIC_KEY = PUBLIC_KEY

# Config for Flask-Mail necessary for user self registration
# MAIL_SERVER = 'smtp.gmail.com'
# MAIL_USE_TLS = True
# MAIL_USERNAME = 'yourappemail@gmail.com'
# MAIL_PASSWORD = 'passwordformail'
# MAIL_DEFAULT_SENDER = 'sender@gmail.com'

# The default user self registration role
# AUTH_USER_REGISTRATION_ROLE = "Public"

# When using OAuth Auth, uncomment to setup provider(s) info
# Google OAuth example:
# OAUTH_PROVIDERS = [{
#   'name':'google',
#     'token_key':'access_token',
#     'icon':'fa-google',
#         'remote_app': {
#             'api_base_url':'https://www.googleapis.com/oauth2/v2/',
#             'client_kwargs':{
#                 'scope': 'email profile'
#             },
#             'access_token_url':'https://accounts.google.com/o/oauth2/token',
#             'authorize_url':'https://accounts.google.com/o/oauth2/auth',
#             'request_token_url': None,
#             'client_id': GOOGLE_KEY,
#             'client_secret': GOOGLE_SECRET_KEY,
#         }
# }]

# When using LDAP Auth, setup the ldap server
AUTH_LDAP_SERVER = "ldap://adcorp.intranet:389"
AUTH_LDAP_USE_TLS = False
AUTH_LDAP_SEARCH = "DC=adcorp,DC=intranet"
AUTH_LDAP_UID_FIELD = "sAMAccountName"
AUTH_LDAP_BIND_USER = "CN=sisairflow0p,OU=Sistemas,OU=Delegacao,DC=adcorp,DC=intranet" 
AUTH_LDAP_BIND_PASSWORD = "@K8s25c10B$wF#"
AUTH_LDAP_FIRSTNAME_FIELD = "givenName"
AUTH_LDAP_LASTNAME_FIELD = "sn"
AUTH_LDAP_EMAIL_FIELD = "mail"
AUTH_LDAP_GROUP_FIELD = "memberOf"
AUTH_USER_REGISTRATION = True
AUTH_USER_REGISTRATION_ROLE = "GRP_AIRFLOW_Viewer"
AUTH_ROLES_MAPPING = { "CN=GRP_AIRFLOW_Admin,OU=Desenvolvimento,OU=Grupos,OU=CVP,DC=adcorp,DC=intranet": ["Admin"], "CN=GRP_AIRFLOW_Viewer,OU=Desenvolvimento,OU=Grupos,OU=CVP,DC=adcorp,DC=intranet": ["Viewer"], "CN=GRP_AIRFLOW_Operator,OU=Desenvolvimento,OU=Grupos,OU=CVP,DC=adcorp,DC=intranet": ["User"], "CN=GRP_AIRFLOW_Developer,OU=Desenvolvimento,OU=Grupos,OU=CVP,DC=adcorp,DC=intranet": ["Op"] }
AUTH_ROLES_SYNC_AT_LOGIN = True
PERMANENT_SESSION_LIFETIME = 1800

# When using OpenID Auth, uncomment to setup OpenID providers.
# example for OpenID authentication
# OPENID_PROVIDERS = [
#    { 'name': 'Yahoo', 'url': 'https://me.yahoo.com' },
#    { 'name': 'AOL', 'url': 'http://openid.aol.com/<username>' },
#    { 'name': 'Flickr', 'url': 'http://www.flickr.com/<username>' },
#    { 'name': 'MyOpenID', 'url': 'https://www.myopenid.com' }]

# ----------------------------------------------------
# Theme CONFIG
# ----------------------------------------------------
# Flask App Builder comes up with a number of predefined themes
# that you can use for Apache Airflow.
# http://flask-appbuilder.readthedocs.io/en/latest/customizing.html#changing-themes
# Please make sure to remove "navbar_color" configuration from airflow.cfg
# in order to fully utilize the theme. (or use that property in conjunction with theme)
# APP_THEME = "bootstrap-theme.css"  # default bootstrap
# APP_THEME = "amelia.css"
# APP_THEME = "cerulean.css"
# APP_THEME = "cosmo.css"
# APP_THEME = "cyborg.css"
# APP_THEME = "darkly.css"
# APP_THEME = "flatly.css"
# APP_THEME = "journal.css"
# APP_THEME = "lumen.css"
# APP_THEME = "paper.css"
# APP_THEME = "readable.css"
# APP_THEME = "sandstone.css"
# APP_THEME = "simplex.css"
# APP_THEME = "slate.css"
# APP_THEME = "solar.css"
# APP_THEME = "spacelab.css"
# APP_THEME = "superhero.css"
# APP_THEME = "united.css"
# APP_THEME = "yeti.css"

import os
import re
from datetime import datetime

from flask import Blueprint, send_from_directory, request, jsonify

# cria blueprint
ui_bp = Blueprint(
    "custom_ui",
    __name__,
    url_prefix=""
)

# rota
@ui_bp.route("/ui.html")
def serve_ui():
    return send_from_directory("/opt/airflow/config/ui", "index.html")


@ui_bp.route("/orquestra/upload-dsx", methods=["POST"])
def upload_dsx():
    """
    Upload de arquivo .dsx para staging (DSX_IMPORT_DIR).
    Usado pela funcionalidade "Importação de Sequence".
    """
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "Arquivo não enviado (campo 'file')"}), 400

    filename = (f.filename or "").strip()
    if not filename.lower().endswith(".dsx"):
        return jsonify({"ok": False, "error": "Apenas arquivos .dsx são permitidos"}), 400

    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"{ts}__{safe}"

    out_dir = os.environ.get("DSX_IMPORT_DIR", "/opt/airflow/dsx/imports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name)
    f.save(out_path)

    return jsonify({"ok": True, "filename": out_name})


# REGISTRO CORRETO (ESSE É O PONTO CRÍTICO)
def init_views(appbuilder):
    appbuilder.get_app.register_blueprint(ui_bp)
