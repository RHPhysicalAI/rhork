{{- define "mediamtx.fullname" -}}
{{- .Release.Name }}
{{- end }}

{{- define "mediamtx.labels" -}}
app.kubernetes.io/name: mediamtx
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "mediamtx.selectorLabels" -}}
app.kubernetes.io/name: mediamtx
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
