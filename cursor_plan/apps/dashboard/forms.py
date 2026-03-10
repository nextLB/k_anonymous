from django import forms


class RunAnonymizationForm(forms.Form):
    k = forms.IntegerField(min_value=2, max_value=50, initial=5, required=True)
    adaptive_k = forms.BooleanField(required=False, initial=False)
    max_length_error_ratio = forms.FloatField(min_value=0.0, max_value=0.5, initial=0.10, required=True)
    direction_diversity_deg = forms.FloatField(min_value=0.0, max_value=180.0, initial=30.0, required=True)
    synthetic_noise_m = forms.FloatField(min_value=0.0, max_value=80.0, initial=8.0, required=True)

