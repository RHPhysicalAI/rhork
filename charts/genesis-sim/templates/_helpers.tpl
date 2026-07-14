{{- define "genesis.fullname" -}}
{{- .Release.Name }}-genesis
{{- end }}

{{- define "genesis.labels" -}}
app.kubernetes.io/name: genesis-sim
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- if .Values.sim }}
genesis-sim/sim: {{ .Values.sim }}
{{- end }}
{{- end }}

{{- define "genesis.selectorLabels" -}}
app.kubernetes.io/name: genesis-sim
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
