from trytond.pool import PoolMeta
from trytond.model import fields
from trytond.pyson import Eval, Bool


class ProductionTemplate(metaclass=PoolMeta):
    __name__ = 'production.template'

    packaging = fields.Boolean('Packaging')
    labeling = fields.Boolean('Labeling')
    product_packaging = fields.Many2One('product.product', 'Product Packing',
       states={
            'invisible': ~Bool(Eval('packaging', -1)),
        },
        domain=[('packaging', '=', True)])

    @classmethod
    def __setup__(cls):
        super().__setup__()

        cls.uom.states = {
            'invisible': Eval('packaging', -1) | Eval('labeling', -1),
            'required': ~(Eval('packaging', -1) | Eval('labeling', -1))
        }
        cls.uom.depends.update({'packaging', 'labeling'})
        cls.quantity.states = {
            'invisible': Eval('packaging', -1) | Eval('labeling', -1),
        }
        cls.quantity.depends.update({'packaging', 'labeling'})
