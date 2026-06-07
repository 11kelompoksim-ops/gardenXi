import calendar
from decimal import Decimal
import json
from datetime import date

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import PurchaseForm, HarvestStockForm, SaleForm, ReturnForm, JournalForm, ReportFilterForm
from .models import Seed, Purchase, HarvestStock, Sale, ReturnTransaction, JournalEntry


def money(value):
    value = int((value or 0))
    return "Rp " + f"{value:,}".replace(",", ".")


def sum_amount(qs, field_name):
    result = qs.aggregate(total=Sum(field_name))["total"]
    return result if result is not None else Decimal("0")

def merge_same_dates(rows):
    last_date = None

    for row in rows:
        current = row["cells"][0]

        if not current:
            continue

        try:
            date_only = current.split(" ")[0]
        except Exception:
            date_only = current

        if date_only == last_date:
            row["cells"][0] = ""
        else:
            last_date = date_only

    return rows

def get_sort_order(request):
    return request.GET.get("sort", "latest")

def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("dashboard")

        messages.error(request, "Username atau password salah.")

    return render(request, "login.html")


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def dashboard(request):
    current_year = int(request.GET.get("year", timezone.localdate().year))

    total_income = sum_amount(Sale.objects.all(), "total_in") + sum_amount(
        JournalEntry.objects.filter(direction=JournalEntry.DEBIT), "amount"
    )
    total_expense = (
        sum_amount(Purchase.objects.all(), "total_out")
        + sum_amount(ReturnTransaction.objects.all(), "total_out")
        + sum_amount(JournalEntry.objects.filter(direction=JournalEntry.KREDIT), "amount")
    )

    purchase_count = Purchase.objects.count()
    sale_count = Sale.objects.count()
    return_count = ReturnTransaction.objects.count()

    labels = []
    values = []

    for month in range(1, 13):
        month_sales = sum_amount(
            Sale.objects.filter(created_at__year=current_year, created_at__month=month),
            "total_in",
        )
        month_journal_debit = sum_amount(
            JournalEntry.objects.filter(
                direction=JournalEntry.DEBIT,
                created_at__year=current_year,
                created_at__month=month,
            ),
            "amount",
        )
        month_purchase = sum_amount(
            Purchase.objects.filter(created_at__year=current_year, created_at__month=month),
            "total_out",
        )
        month_return = sum_amount(
            ReturnTransaction.objects.filter(
                created_at__year=current_year, created_at__month=month
            ),
            "total_out",
        )
        month_journal_kredit = sum_amount(
            JournalEntry.objects.filter(
                direction=JournalEntry.KREDIT,
                created_at__year=current_year,
                created_at__month=month,
            ),
            "amount",
        )

        net = (month_sales + month_journal_debit) - (month_purchase + month_return + month_journal_kredit)
        labels.append(calendar.month_abbr[month])
        values.append(int(net))

    stats = [
        {"label": "Total Pemasukan", "value": money(total_income)},
        {"label": "Total Pengeluaran", "value": money(total_expense)},
        {"label": "Transaksi Pembelian", "value": purchase_count},
        {"label": "Transaksi Penjualan", "value": sale_count},
        {"label": "Transaksi Retur", "value": return_count},
    ]

    context = {
        "selected_year": current_year,
        "prev_year": current_year - 1,
        "next_year": current_year + 1,
        "stats": stats,
        "chart_labels": json.dumps(labels),
        "chart_values": json.dumps(values),
    }
    return render(request, "dashboard.html", context)


@login_required
def purchase_list(request):
    if request.method == "POST":
        form = PurchaseForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            seed, _ = Seed.objects.get_or_create(name=data["seed_name"].strip())
            Purchase.objects.create(
                vendor_name=data["vendor_name"],
                seed=seed,
                qty=data["qty"],
                unit_price=data["unit_price"],
                created_at=data["created_at"],
            )
            messages.success(request, "Data pembelian berhasil disimpan.")
            return redirect("purchases")
    else:
        form = PurchaseForm()
    sort = get_sort_order(request)

    items = Purchase.objects.select_related("seed")

    if sort == "oldest":
        items = items.order_by("created_at")
    else:
        items = items.order_by("-created_at")

    rows = [
        {
            "cells": [
                item.created_at.strftime("%d/%m/%Y %H:%M"),
                item.vendor_name,
                item.seed.name,
                item.qty,
                money(item.unit_price),
                money(item.total_out),
            ],
            "delete_url": reverse("purchase_delete", args=[item.id]),
        }
        for item in items
    ]
    rows = merge_same_dates(rows)
    context = {
        "page_title": "Pembelian",
        "page_subtitle": "Input pembelian barang dan lihat total keluar otomatis.",
        "add_title": "Tambah Pembelian",
        "columns": ["Tanggal", "Vendor", "Barang", "Qty", "Harga per Item", "Total"],
        "form": form,
        "rows": rows,
        "current_sort": sort,
    }
    return render(request, "crud_page.html", context)


@login_required
def purchase_delete(request, pk):
    if request.method == "POST":
        obj = get_object_or_404(Purchase, pk=pk)
        obj.delete()
        messages.success(request, "Data pembelian dihapus.")
    return redirect("purchases")


# ======================== STOK PANEN ========================

def get_harvest_stock(seed):
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
    return total_harvest - total_sold + total_returned


@login_required
def harvest_list(request):
    if request.method == "POST":
        form = HarvestStockForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            seed, _ = Seed.objects.get_or_create(name=data["seed_name"].strip())
            HarvestStock.objects.create(
                seed=seed,
                qty=data["qty"],
                note=data["note"],
                created_at=data["created_at"],
            )
            messages.success(request, "Stok panen berhasil disimpan.")
            return redirect("harvests")
    else:
        form = HarvestStockForm()

    sort = get_sort_order(request)

    items = HarvestStock.objects.select_related("seed")

    if sort == "oldest":
        items = items.order_by("created_at")
    else:
        items = items.order_by("-created_at")
    rows = []
    for item in items:
        stok_tersedia = get_harvest_stock(item.seed)
        rows.append({
            "cells": [
                item.created_at.strftime("%d/%m/%Y %H:%M"),
                item.seed.name,
                item.qty,
                stok_tersedia,
                item.note or "-",
            ],
            "delete_url": reverse("harvest_delete", args=[item.id]),
        })
    rows = merge_same_dates(rows)
    context = {
        "page_title": "Stok Panen",
        "page_subtitle": "Kelola stok hasil panen. Stok ini digunakan sebagai sumber penjualan.",
        "add_title": "Tambah Stok Panen",
        "columns": ["Tanggal", "Barang", "Qty (Kg) Masuk", "Stok Tersedia", "Keterangan"],
        "form": form,
        "rows": rows,
        "current_sort": sort,
    }
    return render(request, "crud_page.html", context)


@login_required
def harvest_delete(request, pk):
    if request.method == "POST":
        obj = get_object_or_404(HarvestStock, pk=pk)
        stok_saat_ini = get_harvest_stock(obj.seed)
        stok_setelah_hapus = stok_saat_ini - obj.qty
        if stok_setelah_hapus < 0:
            messages.error(
                request,
                f"Tidak bisa hapus. Stok {obj.seed.name} akan menjadi negatif "
                f"karena sudah ada penjualan yang menggunakan stok ini."
            )
            return redirect("harvests")
        obj.delete()
        messages.success(request, "Data stok panen dihapus.")
    return redirect("harvests")


# ======================== PENJUALAN ========================

@login_required
def sale_list(request):
    if request.method == "POST":
        form = SaleForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            seed = data["seed"]
            qty = data["qty"]
            unit_price = data["unit_price"]

            stok = get_harvest_stock(seed)
            if qty > stok:
                messages.error(
                    request,
                    f"Stok panen {seed.name} tidak mencukupi. Stok tersedia: {stok}"
                )
                return redirect("sales")

            Sale.objects.create(
                buyer_name=data["buyer_name"],
                seed=seed,
                qty=qty,
                unit_price=unit_price,
                created_at=data["created_at"],
            )
            messages.success(request, "Data penjualan berhasil disimpan.")
            return redirect("sales")
    else:
        form = SaleForm()

    sort = get_sort_order(request)

    items = Sale.objects.select_related("seed")

    if sort == "oldest":
        items = items.order_by("created_at")
    else:
        items = items.order_by("-created_at")
    rows = []
    for item in items:
        rows.append({
            "cells": [
                item.created_at.strftime("%d/%m/%Y %H:%M"),
                item.buyer_name,
                item.seed.name,
                item.qty,
                money(item.unit_price),
                money(item.total_in),
            ],
            "delete_url": reverse("sale_delete", args=[item.id]),
        })
    rows = merge_same_dates(rows)
    context = {
        "page_title": "Penjualan",
        "page_subtitle": "Harga jual diisi manual. Stok mengacu pada stok panen.",
        "add_title": "Tambah Penjualan",
        "columns": ["Tanggal", "Pembeli", "Barang", "Qty", "Harga per Item", "Total"],
        "form": form,
        "rows": rows,
        "current_sort": sort,
    }
    return render(request, "crud_page.html", context)


@login_required
def sale_delete(request, pk):
    if request.method == "POST":
        obj = get_object_or_404(Sale, pk=pk)
        obj.delete()
        messages.success(request, "Data penjualan dihapus.")
    return redirect("sales")


@login_required
def return_list(request):
    if request.method == "POST":
        form = ReturnForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            sale_obj = data["source_sale"]
            qty = data["qty"]

            already_returned = (
                ReturnTransaction.objects
                .filter(source_sale=sale_obj)
                .aggregate(total=Sum("qty"))["total"]
                or 0
            )
            remaining_qty = sale_obj.qty - already_returned

            if qty > remaining_qty:
                messages.error(
                    request,
                    f"Qty retur melebihi sisa transaksi. Maksimal {remaining_qty}"
                )
                return redirect("returns")

            ReturnTransaction.objects.create(
                source_sale=sale_obj,
                buyer_name=sale_obj.buyer_name,
                seed=sale_obj.seed,
                qty=qty,
                unit_price=sale_obj.unit_price,
                created_at=data["created_at"],
            )
            messages.success(request, "Data retur berhasil disimpan.")
            return redirect("returns")
    else:
        form = ReturnForm()

    sort = get_sort_order(request)

    items = ReturnTransaction.objects.select_related("seed", "source_sale")

    if sort == "oldest":
        items = items.order_by("created_at")
    else:
        items = items.order_by("-created_at")

    rows = []
    for item in items:
        rows.append({
            "cells": [
                item.created_at.strftime("%d/%m/%Y %H:%M"),
                item.buyer_name,
                item.seed.name,
                item.qty,
                money(item.unit_price),
                money(item.total_out),
            ],
            "delete_url": reverse("return_delete", args=[item.id]),
        })
    rows = merge_same_dates(rows)
    context = {
        "page_title": "Retur",
        "page_subtitle": "Retur mengikuti transaksi penjualan.",
        "add_title": "Tambah Retur",
        "columns": ["Tanggal", "Pembeli", "Barang", "Qty", "Harga per Item", "Total"],
        "form": form,
        "rows": rows,
        "current_sort": sort,
    }
    return render(request, "crud_page.html", context)


@login_required
def return_delete(request, pk):
    if request.method == "POST":
        obj = get_object_or_404(ReturnTransaction, pk=pk)
        obj.delete()
        messages.success(request, "Data retur dihapus.")
    return redirect("returns")


@login_required
def journal_list(request):
    if request.method == "POST":
        form = JournalForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            JournalEntry.objects.create(
                account_name=data["account_name"],
                direction=data["direction"],
                amount=data["amount"],
                note=data["note"],
                created_at=data["created_at"],
            )
            messages.success(request, "Jurnal manual berhasil disimpan.")
            return redirect("journals")
    else:
        form = JournalForm()

    sort = get_sort_order(request)
    transactions = []

    for item in JournalEntry.objects.all():
        transactions.append({
            "date": item.created_at,
            "source": item.account_name,
            "note": item.note or "-",
            "debit": item.amount if item.direction == JournalEntry.DEBIT else 0,
            "kredit": item.amount if item.direction == JournalEntry.KREDIT else 0,
            "delete_url": reverse("journal_delete", args=[item.id]),
        })

    transactions.sort(
        key=lambda x: x["date"],
        reverse=(sort == "latest")
    )

    rows = []
    for trx in transactions:
        rows.append({
            "cells": [
                trx["date"].strftime("%d/%m/%Y %H:%M"),
                trx["source"],
                trx["note"],
                money(trx["debit"]) if trx["debit"] else "-",
                money(trx["kredit"]) if trx["kredit"] else "-",
            ],
            "delete_url": trx.get("delete_url", "#"),
        })
    rows = merge_same_dates(rows)

    total_debit = sum_amount(
        JournalEntry.objects.filter(direction=JournalEntry.DEBIT),
        "amount"
    )
    total_kredit = sum_amount(
        JournalEntry.objects.filter(direction=JournalEntry.KREDIT),
        "amount"
    )

    balance = (int(total_debit)) - (int(total_kredit))
    balance_status = "Balance" if balance == 0 else "Unbalance"
    balance_color = "success" if balance == 0 else "danger"
    balance_note = (
        f"Lebih {money(balance)}" if balance > 0    
        else "Seimbang" if balance == 0
        else f"Kurang {money(abs(balance))}"
    )

    context = {
        "page_title": "Journalling",
        "page_subtitle": "Arus kas otomatis dari sistem dan manual.",
        "add_title": "Tambah Jurnal Kas",
        "columns": ["Tanggal", "Akun", "Keterangan", "Debit", "Kredit"],
        "form": form,
        "rows": rows,
        "balance": balance_status,
        "balance_note": balance_note,
        "balance_color": balance_color,
        "income": money(total_debit),
        "expense": money(total_kredit),
        "current_sort": sort,
    }
    return render(request, "crud_page.html", context)


@login_required
def journal_delete(request, pk):
    if request.method == "POST":
        obj = get_object_or_404(JournalEntry, pk=pk)
        obj.delete()
        messages.success(request, "Data jurnal dihapus.")
    return redirect("journals")


@login_required
def report_view(request):
    today = timezone.localdate()
    default_start = today.replace(day=1)
    default_end = today

    mode = request.GET.get("mode", "buku_besar")

    from datetime import datetime

    def parse_date(raw, fallback):
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except (ValueError, TypeError):
                continue
        return fallback

    start_date = parse_date(request.GET.get("start_date", ""), default_start)
    end_date = parse_date(request.GET.get("end_date", ""), default_end)

    form = ReportFilterForm(initial={
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
    })

    # Default selected_month untuk jurnal_penyesuaian
    default_month_str = today.strftime("%Y-%m")
    selected_month = request.GET.get("month", default_month_str)
    try:
        peny_year, peny_mo = map(int, selected_month.split("-"))
    except (ValueError, AttributeError):
        peny_year, peny_mo = today.year, today.month
        selected_month = f"{peny_year:04d}-{peny_mo:02d}"

    context = {
        "form": form,
        "mode": mode,
        "end_date_display": end_date.strftime("%d/%m/%Y"),
        "selected_month": selected_month,
    }

    journals = JournalEntry.objects.filter(created_at__date__range=(start_date, end_date))

    gross_in = sum_amount(
        journals.filter(direction=JournalEntry.DEBIT), "amount"
    )
    gross_out = sum_amount(journals.filter(direction=JournalEntry.KREDIT), "amount")
    net = gross_in - gross_out

    # ======================== BUKU BESAR ========================
    if mode == "buku_besar":
        buku_besar = {}

        def add_entry(akun, date, detail, debit=0, kredit=0):
            if akun not in buku_besar:
                buku_besar[akun] = {"rows": [], "saldo": 0}
            buku_besar[akun]["saldo"] += debit - kredit
            buku_besar[akun]["rows"].append({
                "date": date,
                "detail": detail,
                "debit": money(debit) if debit else None,
                "kredit": money(kredit) if kredit else None,
                "saldo": money(buku_besar[akun]["saldo"]),
            })

        for item in journals:
            akun = item.account_name
            if item.direction == JournalEntry.DEBIT:
                add_entry(akun, item.created_at, item.note or "-", debit=item.amount)
            else:
                add_entry(akun, item.created_at, item.note or "-", kredit=item.amount)

        buku_besar_flat = {akun: data["rows"] for akun, data in buku_besar.items()}
        context["buku_besar"] = buku_besar_flat

    # ======================== NERACA SALDO ========================
    elif mode == "neraca_saldo":
        account_names = journals.values_list("account_name", flat=True).distinct()

        neraca_accounts = []
        total_debit_val = Decimal("0")
        total_kredit_val = Decimal("0")

        for account in account_names:
            entries = journals.filter(account_name=account).order_by("created_at")

            account_rows = []
            account_debit = Decimal("0")
            account_kredit = Decimal("0")

            for entry in entries:
                d = entry.amount if entry.direction == JournalEntry.DEBIT else Decimal("0")
                k = entry.amount if entry.direction == JournalEntry.KREDIT else Decimal("0")
                account_debit += d
                account_kredit += k
                account_rows.append({
                    "date": entry.created_at.strftime("%d/%m/%Y"),
                    "note": entry.note or "-",
                    "debit": money(d) if d else None,
                    "kredit": money(k) if k else None,
                })

            total_debit_val += account_debit
            total_kredit_val += account_kredit

            neraca_accounts.append({
                "akun": account,
                "rows": account_rows,
                "total_debit": money(account_debit),
                "total_kredit": money(account_kredit),
            })

        neraca_status = (
            "Seimbang" if total_debit_val == total_kredit_val else "Tidak Seimbang"
        )
        neraca_color = "success" if total_debit_val == total_kredit_val else "danger"

        context.update({
            "neraca_accounts": neraca_accounts,
            "total_debit": money(total_debit_val),
            "total_kredit": money(total_kredit_val),
            "neraca_status": neraca_status,
            "neraca_color": neraca_color,
        })

    # ======================== JURNAL PENYESUAIAN ========================
    elif mode == "jurnal_penyesuaian":
        last_day_num = calendar.monthrange(peny_year, peny_mo)[1]
        peny_last_day = date(peny_year, peny_mo, last_day_num)
        last_day_display = peny_last_day.strftime("%d/%m/%Y")

        # Hanya ambil entry yang diinput tepat di tanggal terakhir bulan
        penyesuaian_journals = JournalEntry.objects.filter(
            created_at__date=peny_last_day
        ).order_by("created_at")

        penyesuaian_rows = []
        for item in penyesuaian_journals:
            penyesuaian_rows.append({
                "date": last_day_display,
                "akun": item.account_name,
                "debit": money(item.amount) if item.direction == JournalEntry.DEBIT else None,
                "kredit": money(item.amount) if item.direction == JournalEntry.KREDIT else None,
            })

        context["penyesuaian_rows"] = penyesuaian_rows
        context["end_date_display"] = last_day_display

    # ======================== JURNAL PENUTUP ========================
    elif mode == "jurnal_penutup":
        penutup_rows = [
            {
                "akun": "Pendapatan",
                "keterangan": "Menutup akun pendapatan ke Ikhtisar Laba Rugi",
                "debit": money(gross_in),
                "kredit": None,
            },
            {
                "akun": "Beban",
                "keterangan": "Menutup akun beban ke Ikhtisar Laba Rugi",
                "debit": None,
                "kredit": money(gross_out),
            },
            {
                "akun": "Ikhtisar Laba Rugi",
                "keterangan": "Laba bersih" if net >= 0 else "Rugi bersih",
                "debit": money(abs(net)) if net < 0 else None,
                "kredit": money(net) if net >= 0 else None,
            },
        ]
        context["penutup_rows"] = penutup_rows

    # ======================== LABA RUGI ========================
    elif mode == "laba_rugi":

        PENDAPATAN_KEYWORDS = ["pendapatan"]
        BEBAN_KEYWORDS = ["beban"]

        def is_pendapatan(name):
            lower = name.lower()
            return any(kw in lower for kw in PENDAPATAN_KEYWORDS)

        def is_beban(name):
            lower = name.lower()
            return any(kw in lower for kw in BEBAN_KEYWORDS)

        account_names = journals.values_list("account_name", flat=True).distinct()

        pendapatan_rows = []
        beban_rows = []
        total_pendapatan = 0
        total_beban = 0

        for account in account_names:
            debit = sum_amount(
                journals.filter(account_name=account, direction=JournalEntry.DEBIT),
                "amount"
            )
            kredit = sum_amount(
                journals.filter(account_name=account, direction=JournalEntry.KREDIT),
                "amount"
            )
            saldo = debit - kredit

            if is_pendapatan(account):
                val = kredit if kredit else abs(saldo)
                total_pendapatan += val
                pendapatan_rows.append({"akun": account, "nominal": money(val)})

            elif is_beban(account):
                val = debit if debit else abs(saldo)
                total_beban += val
                beban_rows.append({"akun": account, "nominal": money(val)})

        laba_bersih = total_pendapatan - total_beban
        lr_label = "Laba Bersih" if laba_bersih >= 0 else "Rugi Bersih"
        lr_color = "success" if laba_bersih >= 0 else "danger"

        context.update({
            "pendapatan_rows": pendapatan_rows,
            "beban_rows": beban_rows,
            "total_pendapatan": money(total_pendapatan),
            "total_beban": money(total_beban),
            "laba_bersih": money(abs(laba_bersih)),
            "lr_label": lr_label,
            "lr_color": lr_color,
        })

    return render(request, "report.html", context)