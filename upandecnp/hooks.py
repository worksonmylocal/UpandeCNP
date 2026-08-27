app_name = "upandecnp"
app_title = "UpandeCNP"
app_publisher = "Upande"
app_description = "Upande Crop Nutrition Planning Module"
app_email = "steve@upande.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "upandecnp",
# 		"logo": "/assets/upandecnp/logo.png",
# 		"title": "UpandeCNP",
# 		"route": "/upandecnp",
# 		"has_permission": "upandecnp.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/upandecnp/css/upandecnp.css"
# app_include_js = "/assets/upandecnp/js/upandecnp.js"

# include js, css files in header of web template
# web_include_css = "/assets/upandecnp/css/upandecnp.css"
# web_include_js = "/assets/upandecnp/js/upandecnp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "upandecnp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "upandecnp/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "upandecnp.utils.jinja_methods",
# 	"filters": "upandecnp.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "upandecnp.install.before_install"
# after_install = "upandecnp.install.after_install"
after_install = "upandecnp.upandecnp.install.after_install"
# Uninstallation
# ------------

before_uninstall = "upandecnp.uninstall.before_uninstall"
# after_uninstall = "upandecnp.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "upandecnp.utils.before_app_install"
# after_app_install = "upandecnp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "upandecnp.utils.before_app_uninstall"
# after_app_uninstall = "upandecnp.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "upandecnp.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
    "Material Request": "upandecnp.upandecnp.utils.farm_permissions.material_request_query",
    "Fertilizer Programme": "upandecnp.upandecnp.utils.farm_permissions.fertilizer_programme_query",
    "Block Fertilizer Plan": "upandecnp.upandecnp.utils.farm_permissions.block_fertilizer_plan_query",
    "Fertilizer Budget": "upandecnp.upandecnp.utils.farm_permissions.fertilizer_budget_query",
    "Fertilizer Application": "upandecnp.upandecnp.utils.farm_permissions.fertilizer_application_query",
    "Production Calendar": "upandecnp.upandecnp.utils.farm_permissions.production_calendar_query",
    "Leaf Analysis": "upandecnp.upandecnp.utils.farm_permissions.leaf_analysis_query",
    "Farm Block": "upandecnp.upandecnp.utils.farm_permissions.farm_block_query",
    "Section": "upandecnp.upandecnp.utils.farm_permissions.section_query",
}

has_permission = {
    "Material Request": "upandecnp.upandecnp.utils.farm_permissions.has_farm_permission",
    "Fertilizer Programme": "upandecnp.upandecnp.utils.farm_permissions.has_farm_permission",
    "Block Fertilizer Plan": "upandecnp.upandecnp.utils.farm_permissions.has_farm_permission",
    "Fertilizer Budget": "upandecnp.upandecnp.utils.farm_permissions.has_farm_permission",
    "Fertilizer Application": "upandecnp.upandecnp.utils.farm_permissions.has_farm_permission",
    "Production Calendar": "upandecnp.upandecnp.utils.farm_permissions.has_farm_permission",
    "Leaf Analysis": "upandecnp.upandecnp.utils.farm_permissions.has_farm_permission",
    "Farm Block": "upandecnp.upandecnp.utils.farm_permissions.has_farm_permission",
    "Section": "upandecnp.upandecnp.utils.farm_permissions.has_farm_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }
doc_events = {
    "Purchase Receipt": {
        "on_submit": "upandecnp.upandecnp.utils.integration.update_budget_on_receipt"
    },
    "Stock Entry": {
        "on_submit": "upandecnp.upandecnp.utils.integration.mark_plan_issued_from_stock_entry"
    },
    "Fertilizer Store Request": {
        "validate": [
            "upandecnp.upandecnp.utils.farm_scope.set_farm_from_block",
            "upandecnp.upandecnp.utils.farm_scope.set_company_from_farm",
        ]
    },
    "Fertilizer Application": {
        "validate": [
            "upandecnp.upandecnp.utils.farm_scope.set_farm_from_block",
            "upandecnp.upandecnp.utils.farm_scope.set_company_from_farm",
        ]
    },
    "Block Fertilizer Plan": {
        "validate": [
            "upandecnp.upandecnp.utils.farm_scope.set_farm_from_block",
            "upandecnp.upandecnp.utils.farm_scope.set_company_from_farm",
        ]
    },
    "Fertilizer Budget": {
        "validate": [
            "upandecnp.upandecnp.utils.farm_scope.set_farm_from_programme",
            "upandecnp.upandecnp.utils.farm_scope.set_company_from_farm",
        ]
    },
    "Farm Block": {
        "validate": "upandecnp.upandecnp.utils.farm_scope.set_company_from_farm"
    },
    "Fertilizer Programme": {
        "validate": "upandecnp.upandecnp.utils.farm_scope.set_company_from_farm"
    },
    "Leaf Analysis": {
        "validate": "upandecnp.upandecnp.utils.farm_scope.set_company_from_farm"
    },
    "Production Calendar": {
        "validate": "upandecnp.upandecnp.utils.farm_scope.set_company_from_farm"
    },
    "Section": {
        "validate": "upandecnp.upandecnp.utils.farm_scope.set_company_from_farm"
    },
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"upandecnp.tasks.all"
# 	],
# 	"daily": [
# 		"upandecnp.tasks.daily"
# 	],
# 	"hourly": [
# 		"upandecnp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"upandecnp.tasks.weekly"
# 	],
# 	"monthly": [
# 		"upandecnp.tasks.monthly"
# 	],
# }
scheduler_events = {
    "daily": [
        "upandecnp.upandecnp.utils.alerts.check_upcoming_applications",
        "upandecnp.upandecnp.utils.alerts.check_low_stock",
        "upandecnp.upandecnp.utils.alerts.check_missed_applications",
    ]
}

# Testing
# -------

# before_tests = "upandecnp.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "upandecnp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "upandecnp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["upandecnp.utils.before_request"]
# after_request = ["upandecnp.utils.after_request"]

# Job Events
# ----------
# before_job = ["upandecnp.utils.before_job"]
# after_job = ["upandecnp.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"upandecnp.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

fixtures = [
    {"dt": "Workflow", "filters": [["name", "=", "Fertilizer Store Request Workflow"]]},
    {"dt": "Workflow State", "filters": [["name", "in", ["Requested", "Approved", "Issued", "Rejected"]]]},
    {"dt": "Workflow Action Master", "filters": [["name", "in", ["Approve", "Reject", "Issue"]]]},
]