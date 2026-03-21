from django import forms


class RunAnonymizationForm(forms.Form):
    k = forms.IntegerField(min_value=2, max_value=50, initial=5, required=True)
    adaptive_k = forms.BooleanField(required=False, initial=False)
    max_length_error_ratio = forms.FloatField(min_value=0.0, max_value=0.5, initial=0.10, required=True)
    direction_diversity_deg = forms.FloatField(min_value=0.0, max_value=180.0, initial=30.0, required=True)
    synthetic_noise_m = forms.FloatField(min_value=0.0, max_value=80.0, initial=8.0, required=True)

    enable_semantic_generalization = forms.BooleanField(required=False, initial=False, label="启用语义泛化")
    enable_pattern_obfuscation = forms.BooleanField(required=False, initial=False, label="启用轨迹模式混淆")
    enable_differential_privacy = forms.BooleanField(required=False, initial=False, label="启用差分隐私")
    dp_epsilon = forms.FloatField(min_value=0.1, max_value=10.0, initial=1.0, required=False, label="差分隐私 ε 值")
    pattern_obfuscation_strength = forms.FloatField(min_value=0.0, max_value=1.0, initial=0.3, required=False, label="模式混淆强度")

