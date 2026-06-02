import calendar
import json
from datetime import date

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import PurchaseForm, SaleForm, ReturnForm, JournalForm, ReportFilterForm
from .models import Seed, Purchase, Sale, ReturnTransaction, JournalEntry


def money(value):
    value = int((value or 0))
    return "Rp " + f"{value:,}".replace(",", ".")


def sum_amount(qs, field_name):
    return qs.aggregate(total=Sum(field_name))["total"] or 0


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
        JournalEntry.objects.filter(direction=JournalEntry.INCOME), "amount"
    )
    total_expense = (
        sum_amount(Purchase.objects.all(), "total_out")
        + sum_amount(ReturnTransaction.objects.all(), "total_out")
        + sum_amount(JournalEntry.objects.filter(direction=JournalEntry.EXPENSE), "amount")
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
        month_journal_in = sum_amount(
            JournalEntry.objects.filter(
                direction=JournalEntry.INCOME,
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
        month_journal_out = sum_amount(
            JournalEntry.objects.filter(
                direction=JournalEntry.EXPENSE,
                created_at__year=current_year,
                created_at__month=month,
            ),
            "amount",
        )

        net = (month_sales + month_journal_in) - (month_purchase + month_return + month_journal_out)
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
            )
            messages.success(request, "Data pembelian berhasil disimpan.")
            return redirect("purchases")
    else:
        form = PurchaseForm()

    items = Purchase.objects.select_related("seed").all()
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

    context = {
        "page_title": "Pembelian",
        "page_subtitle": "Input pembelian benih dan lihat total keluar otomatis.",
        "add_title": "Tambah Pembelian",
        "columns": ["Tanggal", "Vendor", "Benih", "Qty", "Harga per Item", "Total"],
        "form": form,
        "rows": rows,
    }
    return render(request, "crud_page.html", context)


@login_required
def purchase_delete(request, pk):
    if request.method == "POST":
        obj = get_object_or_404(Purchase, pk=pk)
        obj.delete()
        messages.success(request, "Data pembelian dihapus.")
    return redirect("purchases")


@login_required
def sale_list(request):
    def get_stock(seed):
        purchased = (
            Purchase.objects.filter(seed=seed)
            .aggregate(total=Sum("qty"))["total"]
            or 0
        )
        sold = (
            Sale.objects.filter(seed=seed)
            .aggregate(total=Sum("qty"))["total"]
            or 0
        )
        returned = (
            ReturnTransaction.objects.filter(seed=seed)
            .aggregate(total=Sum("qty"))["total"]
            or 0
        )
        return purchased - sold + returned

    if request.method == "POST":
        form = SaleForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            seed = data["seed"]
            qty = data["qty"]
            stock = get_stock(seed)

            if qty > stock:
                messages.error(
                    request,
                    f"Stok {seed.name} tidak mencukupi. Stok tersedia: {stock}"
                )
                return redirect("sales")

            latest_purchase = (
                Purchase.objects
                .filter(seed=seed)
                .order_by("-created_at")
                .first()
            )

            if not latest_purchase:
                messages.error(request, "Benih belum pernah dibeli.")
                return redirect("sales")

            Sale.objects.create(
                buyer_name=data["buyer_name"],
                seed=seed,
                qty=qty,
                unit_price=latest_purchase.unit_price,
            )
            messages.success(request, "Data penjualan berhasil disimpan.")
            return redirect("sales")
    else:
        form = SaleForm()

    items = Sale.objects.select_related("seed").all()
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

    context = {
        "page_title": "Penjualan",
        "page_subtitle": "Harga otomatis mengikuti pembelian terakhir.",
        "add_title": "Tambah Penjualan",
        "columns": ["Tanggal", "Pembeli", "Benih", "Qty", "Harga per Item", "Total"],
        "form": form,
        "rows": rows,
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
            )
            messages.success(request, "Data retur berhasil disimpan.")
            return redirect("returns")
    else:
        form = ReturnForm()

    items = ReturnTransaction.objects.select_related("seed", "source_sale").all()
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

    context = {
        "page_title": "Retur",
        "page_subtitle": "Retur mengikuti transaksi penjualan.",
        "add_title": "Tambah Retur",
        "columns": ["Tanggal", "Pembeli", "Benih", "Qty", "Harga per Item", "Total"],
        "form": form,
        "rows": rows,
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
                direction=data["direction"],
                amount=data["amount"],
                note=data["note"],
            )
            messages.success(request, "Jurnal manual berhasil disimpan.")
            return redirect("journals")
    else:
        form = JournalForm()

    transactions = []

    for item in Sale.objects.select_related("seed").all():
        transactions.append({
            "date": item.created_at,
            "source": "Penjualan",
            "note": f"{item.buyer_name} - {item.seed.name}",
            "income": item.total_in,
            "expense": 0,
        })

    for item in Purchase.objects.select_related("seed").all():
        transactions.append({
            "date": item.created_at,
            "source": "Pembelian",
            "note": f"{item.vendor_name} - {item.seed.name}",
            "income": 0,
            "expense": item.total_out,
        })

    for item in ReturnTransaction.objects.select_related("seed").all():
        transactions.append({
            "date": item.created_at,
            "source": "Retur",
            "note": f"{item.buyer_name} - {item.seed.name}",
            "income": 0,
            "expense": item.total_out,
        })

    for item in JournalEntry.objects.all():
        transactions.append({
            "date": item.created_at,
            "source": "Manual",
            "note": item.note or "-",
            "income": item.amount if item.direction == JournalEntry.INCOME else 0,
            "expense": item.amount if item.direction == JournalEntry.EXPENSE else 0,
            "delete_url": reverse("journal_delete", args=[item.id]),  # ← tambahkan ini
        })

    transactions.sort(key=lambda x: x["date"], reverse=True)

    rows = []
    for trx in transactions:
        rows.append({
            "cells": [
                trx["date"].strftime("%d/%m/%Y %H:%M"),
                trx["source"],
                trx["note"],
                money(trx["income"]) if trx["income"] else "-",
                money(trx["expense"]) if trx["expense"] else "-",
            ],
            "delete_url": trx.get("delete_url", "#")
        })

    total_sales = sum_amount(Sale.objects.all(), "total_in")
    total_purchase = sum_amount(Purchase.objects.all(), "total_out")
    total_return = sum_amount(ReturnTransaction.objects.all(), "total_out")
    manual_income = sum_amount(JournalEntry.objects.filter(direction=JournalEntry.INCOME), "amount")
    manual_expense = sum_amount(JournalEntry.objects.filter(direction=JournalEntry.EXPENSE), "amount")

    total_income = total_sales + manual_income
    total_expense = total_purchase + total_return + manual_expense

    balance = total_income - total_expense
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
        "income": money(total_income),
        "expense": money(total_expense),
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
    initial = {"start_date": today.replace(day=1), "end_date": today}

    mode = request.GET.get("mode", "buku_besar")
    form = ReportFilterForm(request.GET or None, initial=initial)

    # Base context
    context = {
        "form": form,
        "mode": mode,
    }

    if not form.is_valid():
        return render(request, "report.html", context)

    start_date = form.cleaned_data["start_date"]
    end_date = form.cleaned_data["end_date"]

    purchases = Purchase.objects.filter(created_at__date__range=(start_date, end_date)).select_related("seed")
    sales = Sale.objects.filter(created_at__date__range=(start_date, end_date)).select_related("seed")
    returns = ReturnTransaction.objects.filter(created_at__date__range=(start_date, end_date)).select_related("seed")
    journals = JournalEntry.objects.filter(created_at__date__range=(start_date, end_date))

    gross_in = sum_amount(sales, "total_in") + sum_amount(
        journals.filter(direction=JournalEntry.INCOME), "amount"
    )
    gross_out = (
        sum_amount(purchases, "total_out")
        + sum_amount(returns, "total_out")
        + sum_amount(journals.filter(direction=JournalEntry.EXPENSE), "amount")
    )
    net = gross_in - gross_out

    # ======================== BUKU BESAR ========================
    if mode == "buku_besar":
        # Kumpulkan semua transaksi per akun
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

        for item in purchases:
            add_entry("Pembelian", item.created_at, f"{item.vendor_name} - {item.seed.name}", kredit=item.total_out)

        for item in sales:
            add_entry("Penjualan", item.created_at, f"{item.buyer_name} - {item.seed.name}", debit=item.total_in)

        for item in returns:
            add_entry("Retur", item.created_at, f"{item.buyer_name} - {item.seed.name}", kredit=item.total_out)

        for item in journals:
            akun = f"Jurnal {item.get_direction_display()}"
            if item.direction == JournalEntry.INCOME:
                add_entry(akun, item.created_at, item.note or "-", debit=item.amount)
            else:
                add_entry(akun, item.created_at, item.note or "-", kredit=item.amount)

        # Flatten untuk template
        buku_besar_flat = {
            akun: data["rows"]
            for akun, data in buku_besar.items()
        }

        context["buku_besar"] = buku_besar_flat

    # ======================== NERACA SALDO ========================
    elif mode == "neraca_saldo":
        total_penjualan = sum_amount(sales, "total_in")
        total_pembelian = sum_amount(purchases, "total_out")
        total_retur = sum_amount(returns, "total_out")
        manual_in = sum_amount(journals.filter(direction=JournalEntry.INCOME), "amount")
        manual_out = sum_amount(journals.filter(direction=JournalEntry.EXPENSE), "amount")

        neraca_rows = [
            {"akun": "Penjualan", "debit": money(total_penjualan) if total_penjualan else None, "kredit": None},
            {"akun": "Pembelian", "debit": None, "kredit": money(total_pembelian) if total_pembelian else None},
            {"akun": "Retur", "debit": None, "kredit": money(total_retur) if total_retur else None},
        ]

        if manual_in:
            neraca_rows.append({"akun": "Jurnal Masuk (Manual)", "debit": money(manual_in), "kredit": None})
        if manual_out:
            neraca_rows.append({"akun": "Jurnal Keluar (Manual)", "debit": None, "kredit": money(manual_out)})

        total_debit_val = total_penjualan + manual_in
        total_kredit_val = total_pembelian + total_retur + manual_out

        neraca_status = "Seimbang" if total_debit_val == total_kredit_val else "Tidak Seimbang"
        neraca_color = "success" if total_debit_val == total_kredit_val else "danger"

        context.update({
            "neraca_rows": neraca_rows,
            "total_debit": money(total_debit_val),
            "total_kredit": money(total_kredit_val),
            "neraca_status": neraca_status,
            "neraca_color": neraca_color,
        })

    # ======================== JURNAL PENYESUAIAN ========================
    elif mode == "jurnal_penyesuaian":
        # Diambil dari JournalEntry manual saja (jurnal penyesuaian = entri manual)
        penyesuaian_rows = []
        for item in journals:
            penyesuaian_rows.append({
                "date": item.created_at,
                "akun": f"Jurnal {item.get_direction_display()}",
                "nominal": money(item.amount),
                "keterangan": item.note or "-",
            })

        context["penyesuaian_rows"] = penyesuaian_rows

    # ======================== JURNAL PENUTUP ========================
    elif mode == "jurnal_penutup":
        # Tutup akun pendapatan dan beban ke ikhtisar laba rugi
        total_pendapatan = gross_in
        total_beban = gross_out
        laba_rugi = net

        penutup_rows = [
            {
                "akun": "Pendapatan",
                "keterangan": "Menutup akun pendapatan ke Ikhtisar Laba Rugi",
                "debit": money(total_pendapatan),
                "kredit": None,
            },
            {
                "akun": "Beban",
                "keterangan": "Menutup akun beban ke Ikhtisar Laba Rugi",
                "debit": None,
                "kredit": money(total_beban),
            },
            {
                "akun": "Ikhtisar Laba Rugi",
                "keterangan": "Laba bersih" if laba_rugi >= 0 else "Rugi bersih",
                "debit": money(abs(laba_rugi)) if laba_rugi < 0 else None,
                "kredit": money(laba_rugi) if laba_rugi >= 0 else None,
            },
        ]

        context["penutup_rows"] = penutup_rows

    # ======================== LABA RUGI ========================
    elif mode == "laba_rugi":
        records = []

        for item in purchases:
            records.append({
                "date": item.created_at,
                "type": "Pembelian",
                "detail": f"{item.vendor_name} - {item.seed.name}",
                "in_amount": None,
                "out_amount": money(item.total_out),
            })
        for item in sales:
            records.append({
                "date": item.created_at,
                "type": "Penjualan",
                "detail": f"{item.buyer_name} - {item.seed.name}",
                "in_amount": money(item.total_in),
                "out_amount": None,
            })
        for item in returns:
            records.append({
                "date": item.created_at,
                "type": "Retur",
                "detail": f"{item.buyer_name} - {item.seed.name}",
                "in_amount": None,
                "out_amount": money(item.total_out),
            })
        for item in journals:
            records.append({
                "date": item.created_at,
                "type": f"Jurnal {item.get_direction_display()}",
                "detail": item.note or "-",
                "in_amount": money(item.amount) if item.direction == JournalEntry.INCOME else None,
                "out_amount": money(item.amount) if item.direction == JournalEntry.EXPENSE else None,
            })

        records.sort(key=lambda x: x["date"], reverse=True)

        lr_label = "Laba Bersih" if net >= 0 else "Rugi Bersih"
        lr_color = "success" if net >= 0 else "danger"

        context.update({
            "records": records,
            "gross_in": money(gross_in),
            "gross_out": money(gross_out),
            "net": money(abs(net)),
            "lr_label": lr_label,
            "lr_color": lr_color,
        })

    return render(request, "report.html", context)