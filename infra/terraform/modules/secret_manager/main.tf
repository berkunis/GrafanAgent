###############################################################################
# Secret Manager — declares the secret shells Cloud Run services mount, plus
# the IAM binding that lets the runtime service account read them.
#
# See variables.tf for why we deliberately do NOT manage secret *values* in
# Terraform state.
###############################################################################

resource "google_secret_manager_secret" "secret" {
  for_each  = toset(var.secret_names)
  project   = var.project_id
  secret_id = each.value
  labels    = var.labels

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "accessors" {
  for_each = {
    for pair in setproduct(var.secret_names, var.accessors) :
    "${pair[0]}__${pair[1]}" => { secret = pair[0], member = pair[1] }
  }

  project   = var.project_id
  secret_id = google_secret_manager_secret.secret[each.value.secret].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value.member}"
}
