from django import forms

from .models import Seed, JournalEntry, Sale


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")

            if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs["class"] = f"{existing} form-select".strip()
            else:
                field.widget.attrs["class"] = f"{existing} form-control".strip()


class PurchaseForm(BootstrapFormMixin, forms.Form):
    vendor_name = forms.CharField(label="Nama Vendor")
    seed_name = forms.CharField(label="Nama Barang")
    qty = forms.IntegerField(
        label="Qty",
        min_value=1,
    )
    unit_price = forms.DecimalField(
        label="Harga per Item",
        min_value=0,
        max_digits=14,
        decimal_places=2,
    )


class HarvestStockForm(BootstrapFormMixin, forms.Form):
    seed_name = forms.CharField(label="Nama Barang")
    qty = forms.IntegerField(
        label="Qty",
        min_value=1,
    )
    note = forms.CharField(
        label="Keterangan",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["note"].widget = forms.TextInput()
        self.fields["note"].widget.attrs["class"] = "form-control"


class SaleForm(BootstrapFormMixin, forms.Form):
    buyer_name = forms.CharField(label="Nama Pembeli")

    seed = forms.ModelChoiceField(
        label="Barang",
        queryset=Seed.objects.none(),
    )

    qty = forms.IntegerField(
        label="Qty",
        min_value=1,
    )

    unit_price = forms.DecimalField(
        label="Harga Jual per Item",
        min_value=0,
        max_digits=14,
        decimal_places=2,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from django.db.models import Sum
        from .models import HarvestStock, ReturnTransaction

        available_seed_ids = []
        for seed in Seed.objects.all():
            total_harvest = (
                HarvestStock.objects.filter(seed=seed)
                .aggregate(total=Sum("qty"))["total"] or 0
            )
            total_sold = (
                Sale.objects.filter(seed=seed)
                .aggregate(total=Sum("qty"))["total"] or 0
            )
            total_returned = (
                ReturnTransaction.objects.filter(seed=seed)
                .aggregate(total=Sum("qty"))["total"] or 0
            )
            if (total_harvest - total_sold + total_returned) > 0:
                available_seed_ids.append(seed.id)

        self.fields["seed"].queryset = Seed.objects.filter(
            id__in=available_seed_ids
        ).order_by("name")


class ReturnForm(BootstrapFormMixin, forms.Form):
    source_sale = forms.ModelChoiceField(
        label="Transaksi Penjualan",
        queryset=Sale.objects.none(),
    )

    qty = forms.IntegerField(
        label="Qty Retur",
        min_value=1,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["source_sale"].queryset = (
            Sale.objects
            .select_related("seed")
            .order_by("-created_at")
        )

        self.fields["source_sale"].label_from_instance = (
            lambda obj:
            f"{obj.buyer_name} - {obj.seed.name} - Qty {obj.qty}"
        )


class JournalForm(BootstrapFormMixin, forms.Form):
    account_name = forms.CharField(label="Nama Akun")

    direction = forms.ChoiceField(
        label="Posisi",
        choices=JournalEntry.DIRECTION_CHOICES,
    )

    amount = forms.DecimalField(
        label="Nominal",
        min_value=0,
        max_digits=14,
        decimal_places=2,
    )

    note = forms.CharField(
        label="Catatan",
        required=False,
    )

    created_at = forms.DateTimeField(
        label="Tanggal & Jam",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["note"].widget = forms.TextInput()
        self.fields["note"].widget.attrs["class"] = "form-control"


class ReportFilterForm(BootstrapFormMixin, forms.Form):
    start_date = forms.DateField(
        label="Dari",
        widget=forms.DateInput(
            attrs={"type": "date"}
        )
    )

    end_date = forms.DateField(
        label="Sampai",
        widget=forms.DateInput(
            attrs={"type": "date"}
        )
    )