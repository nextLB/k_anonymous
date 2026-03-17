from django import forms


class UploadTrajectoryForm(forms.Form):
    name = forms.CharField(required=False, max_length=200)
    file = forms.FileField(required=True)


class AddSensitivePOIForm(forms.Form):
    name = forms.CharField(required=True, max_length=200)
    category = forms.CharField(required=False, max_length=50)
    center_lat = forms.FloatField(required=True)
    center_lon = forms.FloatField(required=True)
    radius_m = forms.FloatField(required=False, initial=60.0, min_value=5.0)

