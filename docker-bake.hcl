variable "IMAGE_PREFIX" {
  default = "foodmind-"
}

variable "IMAGE_TAG" {
  default = "latest"
}

variable "DEPENDENCY_TAG" {
  default = "local"
}

variable "PYTHON_BASE_IMAGE" {
  default = "foodmind-python-dependencies:local"
}

variable "CONTAINER_PLATFORM" {
  default = "linux/amd64"
}

group "images" {
  targets = ["api", "kestra", "ingestion", "ui"]
}

group "default" {
  targets = ["api", "kestra", "ingestion", "ui"]
}

target "common" {
  context   = "."
  platforms = [CONTAINER_PLATFORM]
}

target "python-dependencies" {
  inherits   = ["common"]
  dockerfile = "Dockerfile.python-base"
  tags       = ["${IMAGE_PREFIX}python-dependencies:${DEPENDENCY_TAG}"]
}

target "python-application" {
  inherits = ["common"]
  args = {
    PYTHON_BASE_IMAGE = PYTHON_BASE_IMAGE
  }
}

target "api" {
  inherits   = ["python-application"]
  dockerfile = "Dockerfile.api"
  tags       = ["${IMAGE_PREFIX}api:${IMAGE_TAG}"]
}

target "kestra" {
  inherits   = ["common"]
  dockerfile = "Dockerfile.kestra"
  tags       = ["${IMAGE_PREFIX}kestra:${IMAGE_TAG}"]
}

target "ingestion" {
  inherits   = ["python-application"]
  dockerfile = "Dockerfile.ingestion"
  tags       = ["${IMAGE_PREFIX}ingestion:${IMAGE_TAG}"]
}

target "ui" {
  inherits   = ["python-application"]
  dockerfile = "Dockerfile.ui"
  tags = [
    "${IMAGE_PREFIX}ui:${IMAGE_TAG}",
    "${IMAGE_PREFIX}ui:latest",
  ]
}
