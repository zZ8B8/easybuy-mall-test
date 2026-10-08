-- ============================================================
--  易淘商城 · 数据库结构
--  MySQL 8.0+ / utf8mb4 / InnoDB
--
--  执行方式（任选其一）：
--    1) 双击项目根目录的「一键启动.bat」，会自动执行本文件
--    2) 命令行： mysql -u root -p < sql/schema.sql
--    3) Navicat：新建查询，把本文件内容粘进去执行
-- ============================================================

CREATE DATABASE IF NOT EXISTS easybuy_mall
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE easybuy_mall;

-- 先删后建，保证每次执行都是干净结构（顺序：先子表后父表）
DROP TABLE IF EXISTS user_coupons;
DROP TABLE IF EXISTS stock_logs;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS carts;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS coupons;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS users;


-- ------------------------------------------------------------
-- 用户表
-- ------------------------------------------------------------
CREATE TABLE users (
    id          INT           NOT NULL AUTO_INCREMENT COMMENT '用户ID',
    username    VARCHAR(50)   NOT NULL                COMMENT '登录名，唯一',
    password    VARCHAR(128)  NOT NULL                COMMENT '密码（本项目为测试靶场，明文存储，便于观察数据）',
    phone       VARCHAR(20)   NULL                    COMMENT '手机号',
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';


-- ------------------------------------------------------------
-- 登录会话表（token -> 用户）
-- ------------------------------------------------------------
CREATE TABLE sessions (
    token       VARCHAR(64)  NOT NULL COMMENT '登录令牌',
    user_id     INT          NOT NULL COMMENT '所属用户',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (token),
    KEY idx_sessions_user (user_id),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录会话表';


-- ------------------------------------------------------------
-- 商品表
-- ------------------------------------------------------------
CREATE TABLE products (
    id          INT            NOT NULL AUTO_INCREMENT COMMENT '商品ID',
    name        VARCHAR(100)   NOT NULL                COMMENT '商品名称',
    category    VARCHAR(30)    NOT NULL                COMMENT '分类',
    price       DECIMAL(10,2)  NOT NULL                COMMENT '单价（元）',
    stock       INT            NOT NULL DEFAULT 0      COMMENT '库存',
    status      VARCHAR(20)    NOT NULL DEFAULT 'ON_SALE' COMMENT '状态：ON_SALE 在售 / OFF_SALE 下架',
    description VARCHAR(500)   NULL                    COMMENT '商品描述',
    created_at  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_products_category (category),
    KEY idx_products_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品表';


-- ------------------------------------------------------------
-- 购物车表
--   同一用户 + 同一商品只有一行，重复加购累加数量
-- ------------------------------------------------------------
CREATE TABLE carts (
    id          INT       NOT NULL AUTO_INCREMENT COMMENT '购物车行ID',
    user_id     INT       NOT NULL                COMMENT '所属用户',
    product_id  INT       NOT NULL                COMMENT '商品ID',
    quantity    INT       NOT NULL                COMMENT '数量',
    created_at  DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_carts_user_product (user_id, product_id),
    CONSTRAINT fk_carts_user    FOREIGN KEY (user_id)    REFERENCES users (id),
    CONSTRAINT fk_carts_product FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='购物车表';


-- ------------------------------------------------------------
-- 优惠券模板表
--   三种券型，靠 type 区分，value 的含义随 type 变化：
--     THRESHOLD 满减券：满 threshold 元减 value 元
--     DISCOUNT  折扣券：打 value 折（value = 0.88 表示 88 折，即实付 88%）
--     FREE      无门槛券：直接减 value 元，不看门槛
-- ------------------------------------------------------------
CREATE TABLE coupons (
    id              INT            NOT NULL AUTO_INCREMENT COMMENT '券ID',
    code            VARCHAR(32)    NOT NULL                COMMENT '券码',
    name            VARCHAR(60)    NOT NULL                COMMENT '券名称',
    type            VARCHAR(20)    NOT NULL                COMMENT 'THRESHOLD 满减 / DISCOUNT 折扣 / FREE 无门槛',
    threshold       DECIMAL(10,2)  NOT NULL DEFAULT 0.00   COMMENT '使用门槛：订单小计需满此金额',
    value           DECIMAL(10,2)  NOT NULL                COMMENT '券值：满减/无门槛=减免金额，折扣=折扣率',
    total_count     INT            NOT NULL DEFAULT 0      COMMENT '发放总量，0 表示不限量',
    claimed_count   INT            NOT NULL DEFAULT 0      COMMENT '已领取数量',
    per_user_limit  INT            NOT NULL DEFAULT 1      COMMENT '每个用户最多可领张数',
    valid_from      DATETIME       NOT NULL                COMMENT '生效时间',
    valid_to        DATETIME       NOT NULL                COMMENT '失效时间',
    status          VARCHAR(20)    NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE 可领 / DISABLED 停发',
    created_at      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_coupons_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='优惠券模板表';


-- ------------------------------------------------------------
-- 用户优惠券表（用户领到的每一张券）
--   状态流转：UNUSED（未使用） -> USED（已使用）
--                               -> EXPIRED（已过期）
--
--   注意：order_id 指向订单，但**故意不加外键约束** ——
--   orders 表也引用本表的 id，两张表互相引用会形成循环依赖，
--   建表顺序无法满足。生产环境里这种「跨表软引用」很常见。
-- ------------------------------------------------------------
CREATE TABLE user_coupons (
    id          INT       NOT NULL AUTO_INCREMENT COMMENT '用户券ID',
    user_id     INT       NOT NULL                COMMENT '持有用户',
    coupon_id   INT       NOT NULL                COMMENT '券模板ID',
    status      VARCHAR(20) NOT NULL DEFAULT 'UNUSED' COMMENT 'UNUSED / USED / EXPIRED',
    order_id    INT       NULL                    COMMENT '使用该券的订单',
    claimed_at  DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '领取时间',
    used_at     DATETIME  NULL                    COMMENT '使用时间',
    PRIMARY KEY (id),
    KEY idx_uc_user (user_id),
    KEY idx_uc_coupon (coupon_id),
    CONSTRAINT fk_uc_user   FOREIGN KEY (user_id)   REFERENCES users (id),
    CONSTRAINT fk_uc_coupon FOREIGN KEY (coupon_id) REFERENCES coupons (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户优惠券表';


-- ------------------------------------------------------------
-- 订单表
--   状态机：PENDING（待支付） -> PAID（已支付）
--                            -> CANCELLED（已取消）
--
--   金额三件套，测试对账时要能对上：
--     total_amount    = 商品小计（各明细单价 × 数量之和）
--     discount_amount = 优惠金额（用券减免的部分）
--     amount          = 实付金额 = total_amount - discount_amount
-- ------------------------------------------------------------
CREATE TABLE orders (
    id               INT            NOT NULL AUTO_INCREMENT COMMENT '订单ID',
    user_id          INT            NOT NULL                COMMENT '下单用户',
    amount           DECIMAL(10,2)  NOT NULL                COMMENT '实付金额（元）',
    total_amount     DECIMAL(10,2)  NOT NULL DEFAULT 0.00   COMMENT '商品小计（元）',
    discount_amount  DECIMAL(10,2)  NOT NULL DEFAULT 0.00   COMMENT '优惠金额（元）',
    user_coupon_id   INT            NULL                    COMMENT '使用的用户券ID（不加外键，见 user_coupons 注释）',
    status           VARCHAR(20)    NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING / PAID / CANCELLED',
    pay_type         VARCHAR(20)    NULL                    COMMENT '支付方式：ALIPAY / WECHAT',
    created_at       DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
    paid_at          DATETIME       NULL                    COMMENT '支付时间',
    PRIMARY KEY (id),
    KEY idx_orders_user (user_id),
    KEY idx_orders_status (status),
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表';


-- ------------------------------------------------------------
-- 订单明细表（下单时把商品名与单价快照进来）
-- ------------------------------------------------------------
CREATE TABLE order_items (
    id            INT            NOT NULL AUTO_INCREMENT,
    order_id      INT            NOT NULL COMMENT '所属订单',
    product_id    INT            NOT NULL COMMENT '商品ID',
    product_name  VARCHAR(100)   NOT NULL COMMENT '下单时的商品名（快照）',
    price         DECIMAL(10,2)  NOT NULL COMMENT '下单时的单价（快照）',
    quantity      INT            NOT NULL COMMENT '数量',
    PRIMARY KEY (id),
    KEY idx_items_order (order_id),
    CONSTRAINT fk_items_order FOREIGN KEY (order_id) REFERENCES orders (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单明细表';


-- ------------------------------------------------------------
-- 库存流水表
--   每一次库存变动都留痕，测试时可用来做「数据一致性」反向核对：
--   期末库存 应等于 期初库存 + 所有流水的和
-- ------------------------------------------------------------
CREATE TABLE stock_logs (
    id          INT          NOT NULL AUTO_INCREMENT,
    product_id  INT          NOT NULL COMMENT '商品ID',
    change_qty  INT          NOT NULL COMMENT '变动量：正数入库，负数出库',
    reason      VARCHAR(30)  NOT NULL COMMENT '原因：ORDER_CREATE / ORDER_CANCEL',
    order_id    INT          NULL     COMMENT '关联订单',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_logs_product (product_id),
    CONSTRAINT fk_logs_product FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='库存流水表';
