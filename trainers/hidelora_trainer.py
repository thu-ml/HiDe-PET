import torch
from timm.models import create_model
from timm.scheduler import create_scheduler
from timm.optim import create_optimizer
import time, datetime, os, sys, random, numpy as np
from datasets import build_continual_dataloader
from engines.hide_lora_wtp_and_tap_engine import train_and_evaluate, evaluate_till_now
import vits.hide_lora_vision_transformer as hide_lora_vision_transformer


def train(args):
    device = torch.device(args.device)
    data_loader, data_loader_per_cls, class_mask, target_task_map = build_continual_dataloader(args)
    print(f"Creating original model: {args.original_model}")
    original_model = create_model(
            args.original_model,
            pretrained=args.pretrained,
            num_classes=args.nb_classes,
            lora=True,
            lora_type='continual',
            rank=args.lora_rank,
            use_mlp_head = args.use_mlp_head,
            mlp_output_dim = args.num_tasks,
        )
    print(f"Creating model: {args.model}")
    model = create_model(args.model,
                         pretrained=args.pretrained,
                         num_classes=args.nb_classes,
                         drop_rate=args.drop,
                         drop_path_rate=args.drop_path,
                         drop_block_rate=None,
                         lora=True, 
                         lora_type=args.lora_type,
                         rank=args.lora_rank, 
                         lora_pool_size=args.size,
                         )
    original_model.to(device)
    model.to(device)

    # all backbobe parameters are frozen for original vit model
    for n, p in original_model.named_parameters():
        p.requires_grad = False
    if args.freeze:
        # freeze args.freeze[blocks, patch_embed, cls_token] parameters
        for n, p in model.named_parameters():
            if n.startswith(tuple(args.freeze)):
                p.requires_grad = False

    print(args)

    if args.eval:
        acc_matrix = np.zeros((args.num_tasks, args.num_tasks))

        for task_id in range(args.num_tasks):
            checkpoint_path = os.path.join(args.output_dir, 'checkpoint/task{}_checkpoint.pth'.format(task_id + 1))
            if os.path.exists(checkpoint_path):
                print('Loading checkpoint from:', checkpoint_path)
                checkpoint = torch.load(checkpoint_path, map_location=device)
                model.load_state_dict(checkpoint['model'])
            else:
                print('No checkpoint found at:', checkpoint_path)
                return
            original_checkpoint_path = os.path.join(args.trained_original_model,
                                                    'checkpoint/task{}_checkpoint.pth'.format(task_id + 1))
            if os.path.exists(original_checkpoint_path):
                print('Loading checkpoint from:', original_checkpoint_path)
                original_checkpoint = torch.load(original_checkpoint_path, map_location=device)
                original_model.load_state_dict(original_checkpoint['model'])
            else:
                print('No checkpoint found at:', original_checkpoint_path)
                return
            _ = evaluate_till_now(model, original_model, data_loader, device,
                                  task_id, class_mask, target_task_map, acc_matrix, args, )

        return

    model_without_ddp = model
    if args.distributed:
        model = torch.nn.parallel.DistributedDataParallel(model, device_ids=[args.gpu], find_unused_parameters=True)
        model_without_ddp = model.module

    n_parameters = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print('number of params:', n_parameters)

    if args.unscale_lr:
        global_batch_size = args.batch_size
    else:
        global_batch_size = args.batch_size * args.world_size
    args.lr = args.lr * global_batch_size / 256.0

    optimizer = create_optimizer(args, model_without_ddp)
    if args.sched != 'constant':
        lr_scheduler, _ = create_scheduler(args, optimizer)
    elif args.sched == 'constant':
        lr_scheduler = None

    criterion = torch.nn.CrossEntropyLoss().to(device)

    print(f"Start training for {args.epochs} epochs")
    start_time = time.time()

    train_and_evaluate(model, model_without_ddp, original_model,
                       criterion, data_loader, data_loader_per_cls,
                       optimizer, lr_scheduler, device, class_mask, target_task_map, args)

    total_time = time.time() - start_time
    total_time_str = str(datetime.timedelta(seconds=int(total_time)))
    print(f"Total training time: {total_time_str}")

    

