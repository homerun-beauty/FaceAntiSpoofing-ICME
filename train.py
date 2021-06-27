# -*- coding: utf-8 -*-
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torchvision
import torchvision.transforms as transforms
import torchvision.models as models
import os
from torch.utils.data import Dataset, DataLoader, ConcatDataset
import numpy as np
from PIL import Image
import sys
from torch.autograd import Variable
import matplotlib.pyplot as plt
from torch.autograd import Function
import argparse
import csv
from sklearn.metrics import roc_auc_score, roc_curve, make_scorer
import torch.optim as optim
import time
import random
import math
from scipy.optimize import brentq
from scipy.interpolate import interp1d

from utils import *
from model import *
from loss import *
from dataset import *

def train(path='./', dataset_path='../', target_domain='oulu', number_folder='1', img_size=256, depth_size=64, batch_size=8, batch_triplet=4, lr=0.0003, n_epoch=100):
    same_seeds(307)
    use_cuda = torch.cuda.is_available()
    device = torch.device("cuda" if use_cuda else "cpu")
    print("finish initialization")
    
    # target:MSU    => 1: i, 2: o, 3: c
    # target:Idiap  => 1: m, 2: o, 3: c
    # target:Oulu   => 1: m, 2: i, 3: c
    # target:Casia  => 1: m, 2: i, 3: o

    shared_spoof_path, spoof_classify_path, shared_content_path, \
    domain1_encoder_path, domain2_encoder_path, domain3_encoder_path, \
    domain_classify_path, decoder_path, depth_map_path = make_model_path(path, target_domain, number_folder) 
    print("finish model path")

    test_dataset, domain1_real_dataset, domain1_print_dataset, domain1_replay_dataset, \
    domain2_real_dataset, domain2_print_dataset, domain2_replay_dataset, domain3_real_dataset, \
    domain3_print_dataset, domain3_replay_dataset = choose_dataset(dataset_path, target_domain, img_size, depth_size)
    print("finish dataset")

    print("test_dataset:{}".format(len(test_dataset)))
    print("domain1_dataset:{}".format(len(domain1_real_dataset + domain1_print_dataset + domain1_replay_dataset)))
    print("domain2_dataset:{}".format(len(domain2_real_dataset + domain2_print_dataset + domain2_replay_dataset)))
    print("domain3_dataset:{}".format(len(domain3_real_dataset + domain3_print_dataset + domain3_replay_dataset)))

    test_loader = DataLoader(test_dataset, batch_size = batch_size, shuffle = False)
    domain1_loader = DataLoader(domain1_real_dataset + domain1_print_dataset + domain1_replay_dataset, batch_size = batch_size, shuffle = True)
    domain2_loader = DataLoader(domain2_real_dataset + domain2_print_dataset + domain2_replay_dataset, batch_size = batch_size, shuffle = True)
    domain3_loader = DataLoader(domain3_real_dataset + domain3_print_dataset + domain3_replay_dataset, batch_size = batch_size, shuffle = True)

    # domain1_real_loader = DataLoader(domain1_real_dataset, batch_size = batch_triplet, shuffle = True)
    # domain1_print_loader = DataLoader(domain1_print_dataset, batch_size = batch_triplet, shuffle = True)
    # domain1_replay_loader = DataLoader(domain1_replay_dataset, batch_size = batch_triplet, shuffle = True)
    # domain2_real_loader = DataLoader(domain2_real_dataset, batch_size = batch_triplet, shuffle = True)
    # domain2_print_loader = DataLoader(domain2_print_dataset, batch_size = batch_triplet, shuffle = True)
    # domain2_replay_loader = DataLoader(domain2_replay_dataset, batch_size = batch_triplet, shuffle = True)
    # domain3_real_loader = DataLoader(domain3_real_dataset, batch_size = batch_triplet, shuffle = True)
    # domain3_print_loader = DataLoader(domain3_print_dataset, batch_size = batch_triplet, shuffle = True)
    # domain3_replay_loader = DataLoader(domain3_replay_dataset, batch_size = batch_triplet, shuffle = True)
    # print("finish data loader")

    domain_a_encoder = torchvision.models.resnet18(pretrained=True).to(device)
    domain_b_encoder = torchvision.models.resnet18(pretrained=True).to(device)
    domain_c_encoder = torchvision.models.resnet18(pretrained=True).to(device)
    shared_content = torchvision.models.resnet18(pretrained=True).to(device)
    shared_spoof = torchvision.models.resnet18(pretrained=True).to(device)
    spoof_classify = spoof_classifier().to(device)
    domain_classify = domain_classifier().to(device)
    decode = decoder().to(device)
    depth_map = depth_decoder().to(device)
    print("finish model")

    """## Training"""

    alpha, beta, gamma = 0.0001, 0.0001, 0.001
    #alpha for spoofing  classify MSE to content and domain
    #gamma for else 
    test_best_auc = 0.0
    test_best_acc = 0.0
    test_best_hter = 0.0

    len_dataloader = min(len(domain1_loader), len(domain2_loader), len(domain3_loader))

    opt_domain_a_encoder = optim.AdamW(domain_a_encoder.parameters(), lr = lr)
    opt_domain_b_encoder = optim.AdamW(domain_b_encoder.parameters(), lr = lr)
    opt_domain_c_encoder = optim.AdamW(domain_c_encoder.parameters(), lr = lr)
    opt_shared_content = optim.AdamW(shared_content.parameters(), lr = lr)
    opt_shared_spoof = optim.AdamW(shared_spoof.parameters(), lr = lr)
    opt_spoof_classify = optim.AdamW(spoof_classify.parameters(), lr = lr)
    opt_domain_classify = optim.AdamW(domain_classify.parameters(), lr = lr)
    opt_decode = optim.AdamW(decode.parameters(), lr = lr)
    opt_depth = optim.AdamW(depth_map.parameters(), lr = lr)
    softmax = nn.Softmax(dim=1)
    class_criterion = nn.CrossEntropyLoss()
    class_criterion_re = MSE()
    mse_loss = MSE()
    simse_loss = SIMSE()
    triplet_loss = nn.TripletMarginLoss(margin=1.0, p=2)

    #plot acc
    plot_auc = []
    plot_acc = []
    plot_hter = []

    print('epoch num = ', n_epoch, ', iter num = ', len_dataloader)

    for epoch in range(n_epoch):
        domain1_loader = DataLoader(domain1_real_dataset + domain1_print_dataset + domain1_replay_dataset, batch_size = batch_size, shuffle = True)
        domain2_loader = DataLoader(domain2_real_dataset + domain2_print_dataset + domain2_replay_dataset, batch_size = batch_size, shuffle = True)
        domain3_loader = DataLoader(domain3_real_dataset + domain3_print_dataset + domain3_replay_dataset, batch_size = batch_size, shuffle = True)
        print('-------------------------------------------------- epoch = {} --------------------------------------------------'.format(str(epoch))) 
        print('-------------------------------------------------- {} Auc = {} --------------------------------------------------'.format(target_domain, str(test_best_auc)))
        print('-------------------------------------------------- {} Acc = {} --------------------------------------------------'.format(target_domain, str(test_best_acc))) 
        print('-------------------------------------------------- {} Hter = {} --------------------------------------------------'.format(target_domain, str(test_best_hter))) 


        e_domain_class_loss = 0.0 
        e_domain_grl_spoof_loss = 0.0 
        e_domain_grl_content_loss = 0.0 
        e_spoof_class_loss = 0.0 
        e_spoof_grl_content_domain_loss = 0.0 
        e_triplet_loss = 0.0 
        e_recon_loss = 0.0 
        
        for i, ((d1_data, d1_depth, d1_label), (d2_data, d2_depth, d2_label), (d3_data, d3_depth, d3_label)) in enumerate(zip(domain1_loader, domain2_loader, domain3_loader)):

            domain_a_encoder.train()
            domain_b_encoder.train()
            domain_c_encoder.train()
            shared_content.train()
            shared_spoof.train()
            spoof_classify.train()
            domain_classify.train()
            decode.train()
            depth_map.train()

            ###Set iter loss###
            domain_class_loss = 0.0 
            domain_grl_spoof_loss = 0.0 
            domain_grl_content_loss = 0.0 
            spoof_class_loss = 0.0 
            spoof_grl_content_domain_loss = 0.0 
            recon_loss = 0.0 
            depth_loss = 0.0

            ###Set data###
            d1_data = d1_data.expand(len(d1_data), 3, img_size , img_size)[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d2_data = d2_data.expand(len(d2_data), 3, img_size , img_size)[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d3_data = d3_data.expand(len(d3_data), 3, img_size , img_size)[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d1_depth = d1_depth[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d2_depth = d2_depth[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d3_depth = d3_depth[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d1_label = d1_label[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d2_label = d2_label[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d3_label = d3_label[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
    
            # 把所有不同domain的資料混在一起
            mixed_data = torch.cat([d1_data, d2_data, d3_data], dim = 0).to(device)
            mixed_depth = torch.cat([d1_depth, d2_depth, d3_depth], dim = 0).to(device)
            mixed_label = torch.cat([d1_label, d2_label, d3_label], dim = 0).to(device)

            mixed_label_domain = torch.tensor([1/3]).repeat(len(d1_data) + len(d2_data) + len(d3_data), 3).to(device)
            mixed_label_re = torch.tensor([1/3]).repeat(len(d1_data) + len(d2_data) + len(d3_data), 3).to(device) # real, print, replay，要讓模型無法分出來

            #設定domain label
            domain_label_true = torch.zeros([len(d1_data) + len(d2_data) + len(d3_data)],dtype=torch.long).to(device)
            domain_label_true[len(d1_data):len(d1_data) + len(d2_data)] = 1
            domain_label_true[len(d2_data) + len(d3_data):] = 2
    
            ###Extract feature###
            spoof_feature = shared_spoof(mixed_data)
            content_feature = shared_content(mixed_data)
            domain1_feature = domain_a_encoder(d1_data)
            domain2_feature = domain_b_encoder(d2_data)
            domain3_feature = domain_c_encoder(d3_data)
            domain_feature = torch.cat([domain1_feature, domain2_feature, domain3_feature], dim = 0).to(device)

            # ###Step 1 : 訓練 Domain Classifier(正向訓練)###
            domain_logit = domain_classify(domain_feature)
            loss_domain = class_criterion(domain_logit, domain_label_true)
            loss = loss_domain
            domain_class_loss += loss 
            e_domain_class_loss += domain_class_loss
            loss.backward()

            opt_domain_a_encoder.step()
            opt_domain_b_encoder.step()
            opt_domain_c_encoder.step()
            opt_domain_classify.step()

            domain_classify.eval() # 不要動
            opt_domain_a_encoder.zero_grad() 
            opt_domain_b_encoder.zero_grad() 
            opt_domain_c_encoder.zero_grad()
            opt_domain_classify.zero_grad() 


            ###Step 2 : 讓Domain Classify GRL回spoof和content###
            #spoof部分
            spoof_domain_logit = softmax(domain_classify(spoof_feature))
            loss_domain = class_criterion_re(spoof_domain_logit, mixed_label_domain) 
            spoof_loss = gamma*loss_domain
            domain_grl_spoof_loss += spoof_loss 
            e_domain_grl_spoof_loss += domain_grl_spoof_loss
            spoof_loss.backward()
            opt_shared_spoof.step()
            opt_shared_spoof.zero_grad() 

            #content部分
            content_domain_logit = softmax(domain_classify(content_feature))
            loss_domain = class_criterion_re(content_domain_logit, mixed_label_domain) 
            content_loss = gamma*loss_domain
            domain_grl_content_loss += content_loss 
            e_domain_grl_content_loss += domain_grl_content_loss
            content_loss.backward()
            opt_shared_content.step()
            opt_shared_content.zero_grad() 

            ###Step 3 : 訓練 Spoof Classify(正向訓練)###
            spoof_feature = shared_spoof(mixed_data) 
            _, loss_class = spoof_classify(spoof_feature, mixed_label, True)
            loss_class *= beta
            spoof_class_loss += loss_class 
            e_spoof_class_loss += spoof_class_loss
            loss_class.backward()
            opt_shared_spoof.step()
            opt_spoof_classify.step()
            opt_shared_spoof.zero_grad() 
            opt_spoof_classify.zero_grad() 
            spoof_classify.eval()

            ###Step 4 : 讓Spoof Classify GRL回content和domain###
            content_feature = shared_content(mixed_data) 
            domain1_feature = domain_a_encoder(d1_data)
            domain2_feature = domain_b_encoder(d2_data)
            domain3_feature = domain_b_encoder(d3_data)
            domain_feature = torch.cat([domain1_feature, domain2_feature, domain3_feature], dim = 0).to(device)

            content_logit = softmax(spoof_classify(content_feature, mixed_label_re, False))
            domain_logit = softmax(spoof_classify(domain_feature, mixed_label_re, False))
            loss_domain = class_criterion_re(content_logit, mixed_label_re)
            loss_content = class_criterion_re(domain_logit, mixed_label_re)
            loss = gamma*loss_content + gamma*loss_domain
            spoof_grl_content_domain_loss += loss
            e_spoof_grl_content_domain_loss += spoof_grl_content_domain_loss
            loss.backward()
            opt_shared_content.step()
            opt_domain_a_encoder.step()
            opt_domain_b_encoder.step()
            opt_domain_c_encoder.step()
            opt_shared_content.zero_grad() 
            opt_domain_a_encoder.zero_grad() 
            opt_domain_b_encoder.zero_grad() 
            opt_domain_c_encoder.zero_grad() 

            ###Step 3.5 : 訓練 depth###
            content_feature = shared_content(mixed_data).view(-1, 1000, 1, 1) ###
            depth_recon = depth_map(content_feature)

            err_sim1 = mse_loss(depth_recon, mixed_depth)
            err_sim2 = simse_loss(depth_recon, mixed_depth)
            err = 0.01*err_sim1 + 0.01*err_sim2
            depth_loss += err

            depth_loss.backward()
            opt_shared_content.step()
            opt_depth.step()
            opt_shared_content.zero_grad()
            opt_depth.zero_grad()
            depth_map.eval()

            ###Step 6 : Recon###
            spoof_feature = shared_spoof(mixed_data) 
            content_feature = shared_content(mixed_data) 
            domain1_feature = domain_a_encoder(d1_data)
            domain2_feature = domain_b_encoder(d2_data)
            domain3_feature = domain_c_encoder(d2_data)

            d1_spoof = spoof_feature[:][:len(d1_data)]
            d2_spoof = spoof_feature[:][len(d1_data):len(d1_data) + len(d2_data)]
            d3_spoof = spoof_feature[:][len(d2_data) + len(d3_data):]

            d1_content = content_feature[:][:len(d1_data)]
            d2_content = content_feature[:][len(d1_data):len(d1_data) + len(d2_data)]
            d3_content = content_feature[:][len(d2_data) + len(d3_data):]

            d1_recon = torch.cat([d1_spoof, d1_content, domain1_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            d2_recon = torch.cat([d2_spoof, d2_content, domain2_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            d3_recon = torch.cat([d3_spoof, d3_content, domain3_feature], dim = 1).view(-1, 3000, 1, 1).to(device)

            d1_recon = decode(d1_recon)
            d2_recon = decode(d2_recon)
            d3_recon = decode(d3_recon)

            err_sim1 = mse_loss(d1_recon, d1_data)
            err_sim2 = simse_loss(d1_recon, d1_data)
            err_sim3 = mse_loss(d2_recon, d2_data)
            err_sim4 = simse_loss(d2_recon, d2_data)
            err_sim5 = mse_loss(d3_recon, d3_data)
            err_sim6 = simse_loss(d3_recon, d3_data)
            
            err = 0.01*err_sim1 + 0.01*err_sim2 + 0.01*err_sim3 + 0.01*err_sim4 + 0.01*err_sim5 + 0.01*err_sim6
            recon_loss += err
            e_recon_loss += recon_loss
            err.backward()

            opt_shared_spoof.step()
            opt_shared_content.step()
            opt_domain_a_encoder.step()
            opt_domain_b_encoder.step()
            opt_domain_c_encoder.step()
            opt_decode.step()
            opt_shared_spoof.zero_grad() 
            opt_shared_content.zero_grad() 
            opt_domain_a_encoder.zero_grad() 
            opt_domain_b_encoder.zero_grad() 
            opt_domain_c_encoder.zero_grad() 
            opt_decode.zero_grad() 

            ''' feature disentanglement '''
            domain_classify.eval()
            spoof_classify.eval()
            d1_data = d1_data.expand(len(d1_data), 3, img_size , img_size)[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d2_data = d2_data.expand(len(d2_data), 3, img_size , img_size)[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d3_data = d3_data.expand(len(d3_data), 3, img_size , img_size)[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d1_label = d1_label[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d2_label = d2_label[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)
            d3_label = d3_label[:min(len(d1_data), len(d2_data), len(d3_data))].to(device)

            domain_label_true = torch.zeros([(len(d1_data) + len(d2_data) + len(d3_data))*2],dtype=torch.long).to(device)
            domain_label_true[len(d1_data)*2:(len(d1_data) + len(d2_data))*2] = 1
            domain_label_true[(len(d2_data) + len(d3_data))*2:] = 2

            mixed_data = torch.cat([d1_data, d2_data, d3_data], dim = 0).to(device)
            spoof_feature = shared_spoof(mixed_data)
            spoof1_feature = spoof_feature[:len(d1_data)]
            spoof2_feature = spoof_feature[len(d1_data):len(d1_data) + len(d2_data)]
            spoof3_feature = spoof_feature[len(d2_data) + len(d3_data):]
            content_feature = shared_content(mixed_data)
            content1_feature = content_feature[:len(d1_data)]
            content2_feature = content_feature[len(d1_data):len(d1_data) + len(d2_data)]
            content3_feature = content_feature[len(d2_data) + len(d3_data):]
            domain1_feature = domain_a_encoder(d1_data)
            domain2_feature = domain_b_encoder(d2_data)
            domain3_feature = domain_c_encoder(d3_data)

            ###for domain###

            d1to2_recon = torch.cat([spoof1_feature, content1_feature, domain2_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            d1to3_recon = torch.cat([spoof1_feature, content1_feature, domain3_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            d2to1_recon = torch.cat([spoof2_feature, content2_feature, domain1_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            d2to3_recon = torch.cat([spoof2_feature, content2_feature, domain3_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            d3to1_recon = torch.cat([spoof3_feature, content3_feature, domain1_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            d3to2_recon = torch.cat([spoof3_feature, content3_feature, domain2_feature], dim = 1).view(-1, 3000, 1, 1).to(device)

            d1to2_recon = decode(d1to2_recon)
            d1to3_recon = decode(d1to3_recon)
            d2to1_recon = decode(d2to1_recon)
            d2to3_recon = decode(d2to3_recon)
            d3to1_recon = decode(d3to1_recon)
            d3to2_recon = decode(d3to2_recon)

            d1to2_recon_feature = domain_b_encoder(d1to2_recon)
            d1to3_recon_feature = domain_c_encoder(d1to3_recon)
            d2to1_recon_feature = domain_a_encoder(d2to1_recon)
            d2to3_recon_feature = domain_c_encoder(d2to3_recon)
            d3to1_recon_feature = domain_a_encoder(d3to1_recon)
            d3to2_recon_feature = domain_b_encoder(d3to2_recon)

            domain_recon_feature = torch.cat([d2to1_recon_feature, d3to1_recon_feature, d1to2_recon_feature, 
                                            d3to2_recon_feature, d1to3_recon_feature, d2to3_recon_feature], dim = 0).to(device)
            domain_recon_logit = domain_classify(domain_recon_feature)
            loss_swap_domain = class_criterion(domain_recon_logit, domain_label_true)

            ###for spoof###
            s1to2_recon = torch.cat([spoof2_feature, content1_feature, domain1_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            s1to3_recon = torch.cat([spoof3_feature, content1_feature, domain1_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            s2to1_recon = torch.cat([spoof1_feature, content2_feature, domain2_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            s2to3_recon = torch.cat([spoof3_feature, content2_feature, domain2_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            s3to1_recon = torch.cat([spoof1_feature, content3_feature, domain3_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            s3to2_recon = torch.cat([spoof2_feature, content3_feature, domain3_feature], dim = 1).view(-1, 3000, 1, 1).to(device)
            s1to2_recon = decode(s1to2_recon)
            s1to3_recon = decode(s1to3_recon)
            s2to1_recon = decode(s2to1_recon)
            s2to3_recon = decode(s2to3_recon)
            s3to1_recon = decode(s3to1_recon)
            s3to2_recon = decode(s3to2_recon)
            s_recon_feature = shared_spoof(torch.cat([s2to1_recon, s3to1_recon, s1to2_recon,
                                                    s3to2_recon, s1to3_recon, s2to3_recon], dim = 0)).to(device)
            # spoof_recon_logit = spoof_classify(s_recon_feature)
            mixed_label = torch.cat([d1_label, d1_label, d2_label, d2_label, d3_label, d3_label], dim = 0).to(device)
            _, loss_swap_spoof = spoof_classify(s_recon_feature, mixed_label, True)

            swap_loss = lambda_function(10, epoch)*(loss_swap_domain + beta*loss_swap_spoof)
            swap_loss.backward() 
            opt_shared_spoof.step()
            opt_domain_a_encoder.step()
            opt_domain_b_encoder.step()
            opt_domain_c_encoder.step()
            opt_shared_spoof.zero_grad() 
            opt_domain_a_encoder.zero_grad() 
            opt_domain_b_encoder.zero_grad()
            opt_domain_c_encoder.zero_grad()

            # domain1_real_loader = DataLoader(domain1_real_dataset, batch_size = batch_size, shuffle = True)
            # domain1_print_loader = DataLoader(domain1_print_dataset, batch_size = batch_size, shuffle = True)
            # domain1_replay_loader = DataLoader(domain1_replay_dataset, batch_size = batch_size, shuffle = True)
            # domain2_real_loader = DataLoader(domain2_real_dataset, batch_size = batch_size, shuffle = True)
            # domain2_print_loader = DataLoader(domain2_print_dataset, batch_size = batch_size, shuffle = True)
            # domain2_replay_loader = DataLoader(domain2_replay_dataset, batch_size = batch_size, shuffle = True)
            # domain3_real_loader = DataLoader(domain3_real_dataset, batch_size = batch_size, shuffle = True)
            # domain3_print_loader = DataLoader(domain3_print_dataset, batch_size = batch_size, shuffle = True)
            # domain3_replay_loader = DataLoader(domain3_replay_dataset, batch_size = batch_size, shuffle = True)

            # ''' triplet loss '''
            # for k, ((d1_real, _, d1_real_label), (d1_print, _, d1_print_label), (d1_replay, _, d1_replay_label), 
            #         (d2_real, _, d2_real_label), (d2_print, _, d2_print_label), (d2_replay, _, d2_replay_label), 
            #         (d3_real, _, d3_real_label), (d3_print, _, d3_print_label), (d3_replay, _, d3_replay_label)) in enumerate( \
            #     zip(domain1_real_loader, domain1_print_loader, domain1_replay_loader, \
            #         domain2_real_loader, domain2_print_loader, domain2_replay_loader, \
            #         domain3_real_loader, domain3_print_loader, domain3_replay_loader \
            #         )):
            #     # print(len(d1_real), len(d1_print), len(d1_replay), len(d1_real), len(d1_print), len(d1_replay), len(d1_real), len(d1_print), len(d1_replay))
            #     data_len = min(len(d1_real), len(d1_print), len(d1_replay), len(d1_real), len(d1_print), len(d1_replay), len(d1_real), len(d1_print), len(d1_replay))
            #     mixed_data = torch.cat([d1_real[:data_len], d1_print[:data_len], d1_replay[:data_len], 
            #                             d2_real[:data_len], d2_print[:data_len], d2_replay[:data_len], 
            #                             d3_real[:data_len], d3_print[:data_len], d3_replay[:data_len]], dim = 0).to(device)
            #     spoof_feature = shared_spoof(mixed_data)
            #     d1_real = spoof_feature[:data_len]
            #     d1_print = spoof_feature[data_len:data_len*2]
            #     d1_replay = spoof_feature[data_len*2:data_len*3]
            #     d2_real = spoof_feature[data_len*3:data_len*4]
            #     d2_print = spoof_feature[data_len*4:data_len*5]
            #     d2_replay = spoof_feature[data_len*5:data_len*6]
            #     d3_real = spoof_feature[data_len*6:data_len*7]
            #     d3_print = spoof_feature[data_len*7:data_len*8]
            #     d3_replay = spoof_feature[data_len*8:]
            #     spoof_triplet_loss = sample_triplet(triplet_loss, d1_real, d1_print, d1_replay, d2_real, d2_print, d2_replay, d3_real, d3_print, d3_replay)
            #     e_triplet_loss += spoof_triplet_loss
            #     print(spoof_triplet_loss)
            #     spoof_triplet_loss.backward()
            #     opt_shared_spoof.step()
            #     opt_shared_spoof.zero_grad()

            print("\r {}/{} domain_class_loss:{:.7f}, depth_loss = {:.7f}, domain_grl_spoof_loss={:.7f}, domain_grl_content_loss={:.7f}, spoof_class_loss={:.4f}, spoof_grl_content_domain_loss={:.7f}, recon_loss = {:.7f}, swap_loss = {:.7f}".format(
                    i+1, len_dataloader, domain_class_loss.item(), depth_loss.item(), domain_grl_spoof_loss.item() , domain_grl_content_loss.item(), spoof_class_loss.item(), 
                    spoof_grl_content_domain_loss.item(), recon_loss.item(), swap_loss.item()), end = "")

        shared_spoof.eval()
        spoof_classify.eval()
        ans = []
        pred = []
        correct = 0
        with torch.no_grad():
            for batch_idx, data in enumerate(test_loader):
                print("\r", batch_idx, '/', len(test_loader), end = "")
                im, label = data
                im, label = im.to(device), label.to(device)
                im = im.expand(im.data.shape[0], 3, 256, 256)

                result = shared_spoof(im)
                features, loss = spoof_classify(result, label, True)
                # print('spoof_class_loss={:.4f}'.format(loss))
                for j in range(len(features)):
                    if label[j].item() == 0:
                        ans.append(1)
                    else:
                        ans.append(0)
                    pred.append(softmax(features)[j][0].item())
                    if label[j].item() == torch.argmax(features[j], dim=0).item():
                        correct += 1
        test_auc = roc_auc_score(ans, pred)
        _, test_hter = HTER(np.array(pred), np.array(ans))
        print('Final {} test auc = {}'.format(target_domain, test_auc))
        print('Final {} test acc = {}'.format(target_domain, correct/len(test_dataset)))
        print('Final {} test hter = {}'.format(target_domain, test_hter))
        plot_auc.append(test_auc)
        plot_acc.append(test_auc)
        plot_hter.append(test_hter)
        if test_auc > test_best_auc:
            test_best_auc = test_auc
            test_best_acc = correct/len(test_dataset)
            test_best_hter = test_hter
            torch.save(shared_spoof, shared_spoof_path)
            torch.save(spoof_classify, spoof_classify_path)
            torch.save(shared_content, shared_content_path)
            torch.save(depth_map, depth_map_path)
            torch.save(domain_a_encoder, domain1_encoder_path)
            torch.save(domain_b_encoder, domain2_encoder_path)
            torch.save(domain_c_encoder, domain3_encoder_path)
            torch.save(domain_classify, domain_classify_path)
            torch.save(decode, decoder_path)
            print('{}: save model'.format(target_domain))

        if test_auc > test_best_auc:
            test_best_auc = test_auc
            test_best_acc = correct/len(test_dataset)
            torch.save(shared_spoof, shared_spoof_path)
            torch.save(spoof_classify, spoof_classify_path)
            torch.save(shared_content, shared_content_path)
            torch.save(depth_map, depth_map_path)
            torch.save(domain_a_encoder, domain1_encoder_path)
            torch.save(domain_b_encoder, domain2_encoder_path)
            torch.save(domain_c_encoder, domain3_encoder_path)
            torch.save(domain_classify, domain_classify_path)
            torch.save(decode, decoder_path)
            print('{}: save model'.format(target_domain))