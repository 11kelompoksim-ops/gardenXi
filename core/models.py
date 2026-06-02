from decimal import Decimal

from django.db import models


class Seed(models.Model):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Purchase(models.Model):
    vendor_name = models.CharField(max_length=120)
    seed = models.ForeignKey(Seed, on_delete=models.PROTECT, related_name="purchases")
    qty = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    total_out = models.DecimalField(max_digits=14, decimal_places=2, editable=False, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.total_out = Decimal(self.qty) * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vendor_name} - {self.seed.name}"


class HarvestStock(models.Model):
    seed = models.ForeignKey(Seed, on_delete=models.PROTECT, related_name="harvest_stocks")
    qty = models.PositiveIntegerField()
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.seed.name} - {self.qty}"


class Sale(models.Model):
    buyer_name = models.CharField(max_length=120)
    seed = models.ForeignKey(Seed, on_delete=models.PROTECT, related_name="sales")
    qty = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    total_in = models.DecimalField(max_digits=14, decimal_places=2, editable=False, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.total_in = Decimal(self.qty) * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.buyer_name} - {self.seed.name} - {self.qty}"


class ReturnTransaction(models.Model):
    source_sale = models.ForeignKey(
        Sale,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="returns",
    )
    buyer_name = models.CharField(max_length=120)
    seed = models.ForeignKey(Seed, on_delete=models.PROTECT, related_name="returns")
    qty = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    total_out = models.DecimalField(max_digits=14, decimal_places=2, editable=False, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.total_out = Decimal(self.qty) * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.buyer_name} - {self.seed.name}"


class JournalEntry(models.Model):
    INCOME = "IN"
    EXPENSE = "OUT"

    DIRECTION_CHOICES = [
        (INCOME, "Pemasukan"),
        (EXPENSE, "Pengeluaran"),
    ]

    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_direction_display()} - {self.amount}"