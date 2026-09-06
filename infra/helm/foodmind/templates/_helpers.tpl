{{- define "foodmind.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{- define "foodmind.labels" -}}
app.kubernetes.io/name: {{ include "foodmind.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: Helm
{{- end -}}

{{- define "foodmind.selectorLabels" -}}
app.kubernetes.io/name: {{ include "foodmind.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
