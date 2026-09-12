# Explicit opt-in profile for a complete, destructive teardown.
#
# Apply this profile once before running destroy. That updates both provider-
# level and cloud API-level deletion safeguards before Terraform starts
# deleting dependent resources.
force_destroy                 = true
gke_deletion_protection       = false
cloud_sql_deletion_protection = false
