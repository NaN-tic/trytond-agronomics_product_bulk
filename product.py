# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import functools
from trytond.model import fields, ModelSQL, ModelView
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval, Bool, Id
from trytond.transaction import Transaction
from trytond.tools import grouped_slice
from trytond.model.exceptions import AccessError
from trytond.i18n import gettext

NON_MEASURABLE = ['service']

def check_no_move(func):

    @functools.wraps(func)
    def decorator(cls, *args):
        pool = Pool()
        Product =  pool.get('product.product')
        Template =  pool.get('product.template')
        ProductPackage = pool.get('product.product-product.packaging')

        transaction = Transaction()
        if (transaction.user != 0 and transaction.context.get('_check_access')):
            actions = iter(args)
            for records, values in zip(actions, actions):
                for field, msg in Product._modify_no_move:
                    products = []
                    if records and isinstance(records[0], Template):
                        for record in records:
                            products += record.products
                    if records and isinstance(records[0], ProductPackage):
                        products = [x.product for x in records]
                    if field in values:
                        if Product.find_move(products):
                            raise AccessError(gettext(msg))
                        break
        func(cls, *args)
    return decorator


class ProductProductPackaging(ModelSQL, ModelView):
    "Product - Product Packaging"
    __name__ = 'product.product-product.packaging'

    production_template = fields.Many2One('production.template',
        'Production Template', required=True, ondelete='CASCADE',
            states ={
                'readonly': Bool(Eval('packaged_product')),
            },
            domain=[
             ['OR', ('packaging', '=', True), ('labeling', '=', True)],
             ('inputs_products', 'in', Eval('product')),
            ])
    product = fields.Many2One('product.product', 'Product', required=True)
    packaged_product = fields.Many2One('product.product', 'Packaged Product',
        readonly=True)

    @classmethod
    @check_no_move
    def write(cls, *args):
        super().write(*args)


class Template(metaclass=PoolMeta):
    __name__ = 'product.template'

    bulk_type = fields.Boolean('Bulk')
    bulk_quantity = fields.Function(fields.Float('Bulk Quantity',
        help="The amount of bulk stock in the location."),
        'sum_product')
    packaging = fields.Boolean('Packaging')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._modify_no_move = [
            ('bulk_type', 'mg_bulk_with_moves'),
            ]

    def sum_product(self, name):
        if name in ('bulk_quantity'):
            sum_ = 0.
            for product in self.products:
                sum_ += getattr(product, name)
            return sum_
        return super().sum_product(name)

    @classmethod
    @check_no_move
    def write(cls, *args):
        super().write(*args)


class Product(metaclass=PoolMeta):
    __name__ = 'product.product'

    bulk_type = fields.Function(fields.Boolean('Bulk'), 'get_bulk',
        searcher='search_bulk_type')
    bulk_product = fields.Many2One('product.product', 'Bulk Product',
        states= {
            'readonly': ~Eval('active', True),
            })
    bulk_quantity = fields.Function(fields.Float('Bulk Quantity',
        help="The amount of bulk stock in the location."),
        'get_bulk_quantity', searcher='search_bulk_quantity')
    packaging_products = fields.One2Many('product.product-product.packaging',
        'product', 'Packaging Products')
    capacity_pkg = fields.Float('Capacity', digits=(16, Eval('capacity_digits',
        2)), states={
            'invisible': Eval('type').in_(NON_MEASURABLE),
            })
    capacity_uom = fields.Many2One('product.uom', 'Capacity Uom',
        domain=[('symbol', '=', 'l')],
        states={
            'invisible': Eval('type').in_(NON_MEASURABLE),
            'required': Bool(Eval('capacity')),
            })
    capacity_digits = fields.Function(fields.Integer('Capacity Digits'),
        'on_change_with_capacity_digits')
    netweight = fields.Float('Net Weight',
        digits=(16, Eval('netweight_digits', 2)),
        states={
            'invisible': Eval('type').in_(NON_MEASURABLE),
            })
    netweight_uom = fields.Many2One('product.uom', 'Net Weight Uom',
        domain=[('category', '=', Id('product', 'uom_cat_weight'))],
        states={
            'invisible': Eval('type').in_(NON_MEASURABLE),
            'required': Bool(Eval('netweight')),
            })
    netweight_digits = fields.Function(fields.Integer('Net Weight Digits'),
        'on_change_with_netweight_digits')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._modify_no_move = [
            ('bulk', 'template.bulk_with_moves'),
            ]

        cls._buttons.update({
                'create_packaging_products': {
                    'invisible': ~Eval('active', True)
                },
            })

    @fields.depends('capacity_uom')
    def on_change_with_capacity_digits(self, name=None):
        return (self.capacity_uom.digits if self.capacity_uom
            else self.default_capacity_digits())

    @staticmethod
    def default_capacity():
        return 0.

    @staticmethod
    def default_capacity_uom():
        return Pool().get('ir.model.data').get_id('product', 'uom_liter')

    @staticmethod
    def default_capacity_digits():
        return 2

    @fields.depends('netweight_uom')
    def on_change_with_netweight_digits(self, name=None):
        return (self.netweight_uom.digits if self.netweight_uom
            else self.default_netweight_digits())

    @staticmethod
    def default_netweight_digits():
        return 2

    def get_bulk(self, name=None):
        return self.template.bulk_type

    @classmethod
    def search_bulk_type(cls, name, clause):
        return [('template.%s' % name ,) + tuple(clause[1:])]

    @classmethod
    @ModelView.button
    def create_packaging_products(cls, products):
        Product = Pool().get('product.product')
        Bom = Pool().get('production.bom')
        BOMInput = Pool().get('production.bom.input')
        BOMOutput = Pool().get('production.bom.output')
        Uom = Pool().get('product.uom')
        ProductPackaging = Pool().get('product.product-product.packaging')
        ProductBom = Pool().get('product.product-production.bom')
        Variety = Pool().get('product.variety')

        uom_unit, = Uom.search([('symbol', 'like', 'u')])
        uom_kg, = Uom.search([('symbol', 'like', 'kg')])
        product_to_save = []
        bom_to_save = []
        output_to_save = []


        for product in products:
            for package_product in product.packaging_products:
                inputs = []
                if package_product.packaged_product:
                    continue
                production_template = package_product.production_template
                new_name = (product.name +
                        ' (' + production_template.name + ')')
                if production_template.packaging:
                    pack_product = production_template.product_packaging
                    capacity = pack_product.capacity_pkg or 1
                    netweight = round(capacity/ 1000, uom_kg.digits)
                    weight = round(netweight + (pack_product.weight
                        if pack_product.weight else 0), uom_kg.digits)
                if production_template.labeling:
                    capacity = product.capacity
                    netweight = product.netweight
                    weight = product.weight
                    pack_product = None

                if not production_template.outputs:
                    continue

                template = production_template.outputs[0]
                output_product = Product()
                output_product.template = template
                output_product.capacity_pkg = capacity
                output_product.netweight = netweight
                output_product.netweight_uom = uom_kg
                output_product.weight = weight
                output_product.weight_uom = uom_kg
                output_product.bulk_product = (product.bulk_product and
                    product.bulk_product.id or product.id)
                output_product.denominations_of_origin = list(
                    product.denominations_of_origin)
                output_product.ecologicals = list(
                    product.ecologicals)
                output_product.vintages = list(product.vintages)
                varieties = []
                for variety in product.varieties:
                    new_variety = Variety()
                    new_variety.variety = variety.variety
                    new_variety.percent = variety.percent
                    varieties.append(new_variety)
                output_product.varieties=varieties
                output_product.save()

                package_product.packaged_product = output_product
                output_to_save.append(package_product)

                quantity = 1
                if pack_product:
                    quantity = pack_product.capacity_pkg
                bom = Bom(name=new_name)
                bulk_input = BOMInput(
                    bom=bom,
                    product=product,
                    uom=product.default_uom,
                    quantity=quantity)
                inputs = [bulk_input]
                if pack_product:
                    package_input = BOMInput(
                        bom=bom,
                        product=pack_product,
                        uom=pack_product.default_uom,
                        quantity=1.0)
                    inputs.append(package_input)

                for extra in  production_template.enology_products:
                    extra_input = BOMInput(
                        bom=bom,
                        product=extra.product,
                        uom=extra.product.default_uom,
                        quantity=extra.quantity)
                    inputs.append(extra_input)

                output = BOMOutput(
                    bom=bom,
                    product=output_product.id,
                    uom=uom_unit,
                    quantity=1.0)

                bom.inputs = inputs
                bom.outputs = [output]
                bom_to_save.append(bom)

                product_bom = ProductBom()
                product_bom.bom = bom
                product_bom.product = output_product
                product_to_save.append(product_bom)

            Bom.save(bom_to_save)
            ProductBom.save(product_to_save)
            ProductPackaging.save(output_to_save)


    @classmethod
    def get_bulk_quantity(cls, products, name):
        pool = Pool()
        Location = pool.get('stock.location')
        Product = pool.get('product.product')
        Date = pool.get('ir.date')
        today = Date().today()

        res = {}
        products_ids = []
        for product in products:
            res[product.id] = 0

        location_ids = Transaction().context.get('locations')
        if not location_ids:
            locations = Location.search(['type', '=', 'warehouse'])
            location_ids = [x.storage_location.id for x in locations
                            if x.storage_location]

        output_products = []
        bulk_products = []
        for prod in products:
            if prod.bulk_type and not prod.bulk_product:
                bulk_products.append(prod)
                continue
            if prod.bulk_product:
                bulk_products.append(prod.bulk_product)
            output_products.append(prod)

        bulk_products_ids = [x.id for x in bulk_products]
        output_products += Product.search([
                ('bulk_product', 'in', bulk_products_ids)
                ])
        output_products = list(set(output_products))
        output_products_ids = [x.id for x in output_products]
        products_ids += [x.id for x in output_products]
        with Transaction().set_context(locations=location_ids,
                    stock_date_end=today,
                    with_childs=True,
                    check_access=False):

            output_quantity = cls._get_quantity(output_products, 'quantity',
                location_ids, grouping=('product',),
                grouping_filter=(output_products_ids,))
            bulk_quantity = cls._get_quantity(bulk_products, 'quantity',
                location_ids, grouping=('product',) ,
                grouping_filter=(bulk_products_ids,))

        for product in products:
            prod = product.bulk_product if product.bulk_product else product
            res[product.id] += bulk_quantity.get(prod.id ,0)
            for output in output_products:
                if output.bulk_product != prod:
                    continue
                res[product.id] += (output_quantity.get(output.id ,0)
                        * (output.capacity_pkg if output.capacity_pkg else 1))

        return res

    @classmethod
    def search_bulk_quantity(cls, name, domain=None):
        location_ids = Transaction().context.get('locations')
        return cls._search_quantity('quantity', location_ids, domain,
            grouping=('bulk_product', 'product',))

    @classmethod
    @check_no_move
    def write(cls, *args):
        super().write(*args)

    @classmethod
    def find_moves(cls, products):
        Move = Pool().get('stock.move')
        for sub_records in grouped_slice(products):
            rows = Move.search([
                    ('product', 'in', list(map(int, sub_records))),
                    ],
                limit=1, order=[])
            if rows:
                return rows
        return False

