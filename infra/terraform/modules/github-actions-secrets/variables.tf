variable "repository" {
  description = "GitHub repository name that receives the Actions secret."
  type        = string
}

variable "openai_api_key" {
  description = "OpenAI API key stored as the repository OPENAI_API_KEY Actions secret."
  type        = string
  sensitive   = true
  default     = null
}
