from django.forms import ModelForm
from im.models import Category ,Product
from django import forms

class categoryForm(ModelForm):
    class Meta:
        model = Category 
        fields = '__all__'

class productForm(ModelForm):
    class Meta:
        model =Product 
        fields = '__all__'

class ProductCSVUploadForm(forms.Form):
    csv_file = forms.FileField(
        label='Select CSV File',
        help_text='Upload a CSV file with product data',
        widget=forms.FileInput(attrs={'accept': '.csv'})
    )
    skip_errors = forms.BooleanField(
        label='Skip rows with errors',
        required=False,
        initial=False,
        help_text='If checked, import will continue even if some rows fail'
    )
