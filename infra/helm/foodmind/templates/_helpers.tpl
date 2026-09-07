{{- define "foodmind.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{- define "foodmind.labels" -}}
app.kubernetes.io/name: {{ include "foodmind.name" . }}
# Keep selectors stable while the single legacy release is migrated into
# component releases. Kubernetes rejects a Deployment/StatefulSet selector
# change, and these resources were originally installed with this value.
app.kubernetes.io/instance: foodmind
app.kubernetes.io/managed-by: Helm
{{- end -}}

{{- define "foodmind.selectorLabels" -}}
app.kubernetes.io/name: {{ include "foodmind.name" . }}
app.kubernetes.io/instance: foodmind
{{- end -}}
