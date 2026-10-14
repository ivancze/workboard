# Emails the billing account's administrators, which is the operator. Covers
# the whole billing account, not only this project.
resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account
  display_name    = "Workboard, RM65 a month"

  budget_filter {
    # Count spend before the trial's credits, or it reads $0 until they run out.
    credit_types_treatment = "EXCLUDE_ALL_CREDITS"
  }

  amount {
    specified_amount {
      # The billing account's currency, which the budget must match. About
      # $15 at the time of writing.
      currency_code = "MYR"
      units         = "65"
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 1.0
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  depends_on = [google_project_service.apis]
}
