{{- define "viewer.fullname" -}}
{{- .Release.Name }}-viewer
{{- end }}

{{- define "viewer.labels" -}}
app.kubernetes.io/name: gz-viewer
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "viewer.selectorLabels" -}}
app.kubernetes.io/name: gz-viewer
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
