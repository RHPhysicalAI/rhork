{{- define "coturn.fullname" -}}
{{- .Release.Name }}-coturn
{{- end }}

{{- define "coturn.labels" -}}
app.kubernetes.io/name: coturn
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
